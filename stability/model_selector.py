import time, logging, asyncio, httpx
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger('ThzRoom.Stability.ModelSelector')
OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
DEFAULT_FALLBACK_MODEL = 'qwen2.5:7b'
MAX_STRIKES_BEFORE_DEGRADE = 1
COOLDOWN_SECONDS = 180.0

@dataclass
class ModelHealthRecord:
    name: str
    size_bytes: int
    success_count: int = 0
    failure_count: int = 0
    total_latency_sec: float = 0.0
    avg_latency_sec: float = 0.0
    is_healthy: bool = True
    disabled_until: float = 0.0
    last_error: Optional[str] = None

    def record_success(self, latency_sec: float):
        self.success_count += 1
        self.total_latency_sec += latency_sec
        self.avg_latency_sec = self.total_latency_sec / self.success_count
        self.failure_count = max(0, self.failure_count - 1)
        self.is_healthy = True
        self.last_error = None

    def record_failure(self, reason: str, cooldown_seconds: float = COOLDOWN_SECONDS):
        self.failure_count += 1
        self.last_error = reason
        if self.failure_count >= MAX_STRIKES_BEFORE_DEGRADE:
            self.is_healthy = False
            self.disabled_until = time.time() + cooldown_seconds
            logger.warning(f'[ADAPTIVE-MODEL] Modelo {self.name} degradado por {cooldown_seconds:.0f}s: {reason}')

    def is_available(self) -> bool:
        if self.is_healthy:
            return True
        if time.time() >= self.disabled_until:
            self.is_healthy = True
            self.failure_count = 0
            logger.info(f'[ADAPTIVE-MODEL] Cooldown de {self.name} expirou. Reabilitado.')
            return True
        return False

class AdaptiveModelSelector:
    def __init__(self, ollama_url: str = OLLAMA_BASE_URL):
        self.ollama_url = ollama_url.rstrip('/')
        self.health_registry: Dict[str, ModelHealthRecord] = {}
        self.cached_models: List[Dict[str, Any]] = []
        self.last_cache_time: float = 0.0

    async def fetch_local_models(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self.cached_models and (now - self.last_cache_time < 30.0):
            return self.cached_models
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f'{self.ollama_url}/api/tags', timeout=5.0)
                resp.raise_for_status()
                data = resp.json().get('models', [])
                chat_models = []
                for m in data:
                    name = m.get('name', '')
                    if any(bad in name.lower() for bad in ['embed', 'bge', 'bert']):
                        continue
                    chat_models.append({'name': name, 'size': m.get('size', 0)})
                chat_models.sort(key=lambda x: x['size'], reverse=True)
                self.cached_models = chat_models
                self.last_cache_time = now
                for m in chat_models:
                    name = m['name']
                    if name not in self.health_registry:
                        self.health_registry[name] = ModelHealthRecord(name=name, size_bytes=m['size'])
                return chat_models
        except Exception as e:
            logger.warning(f'[ADAPTIVE-MODEL] Erro tags: {e}')
            if not self.cached_models:
                return [{'name': DEFAULT_FALLBACK_MODEL, 'size': 4700000000}]
            return self.cached_models

    async def get_model_ladder(self, preferred_model: Optional[str] = None) -> List[str]:
        models = await self.fetch_local_models()
        model_names = [m['name'] for m in models]
        ladder: List[str] = []
        if preferred_model and preferred_model != 'auto':
            matched = next((name for name in model_names if preferred_model in name or name in preferred_model), preferred_model)
            ladder.append(matched)
        for name in model_names:
            if name not in ladder:
                ladder.append(name)
        if not ladder:
            ladder = [DEFAULT_FALLBACK_MODEL]
        return ladder

    async def get_best_healthy_model(self, preferred_model: Optional[str] = None) -> str:
        ladder = await self.get_model_ladder(preferred_model)
        for model_name in ladder:
            rec = self.health_registry.get(model_name)
            if rec is None or rec.is_available():
                return model_name
        return ladder[-1]

    async def infer_with_adaptive_fallback(self, messages: List[Dict[str, str]], options: Optional[Dict[str, Any]] = None, preferred_model: Optional[str] = None, step_timeout_sec: float = 120.0, progress_callback: Optional[Callable[[Dict[str, Any]], Any]] = None) -> Tuple[str, str, float]:
        ladder = await self.get_model_ladder(preferred_model)
        opts = options.copy() if options else {}
        last_error = None
        for idx, model_to_try in enumerate(ladder):
            rec = self.health_registry.setdefault(model_to_try, ModelHealthRecord(name=model_to_try, size_bytes=0))
            if not rec.is_available() and idx < len(ladder) - 1:
                logger.info(f'[ADAPTIVE-MODEL] Pulando {model_to_try} (em cooldown)')
                continue
            payload = {'model': model_to_try, 'messages': messages, 'stream': False, 'options': opts}
            t_start = time.time()
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(f'{self.ollama_url}/api/chat', json=payload, timeout=step_timeout_sec)
                    resp.raise_for_status()
                    content = resp.json().get('message', {}).get('content', '').strip()
                    latency = time.time() - t_start
                    rec.record_success(latency)
                    return content, model_to_try, latency
            except (httpx.TimeoutException, TimeoutError) as timeout_err:
                latency = time.time() - t_start
                reason = f'Timeout ({latency:.1f}s excedeu limite de {step_timeout_sec}s)'
                rec.record_failure(reason)
                last_error = timeout_err
                if idx + 1 < len(ladder):
                    next_model = ladder[idx + 1]
                    logger.warning(f'[ADAPTIVE-MODEL] {model_to_try} estourou tempo. Abaixando regua para {next_model}')
                    if progress_callback:
                        evt = {'type': 'model_degraded', 'from_model': model_to_try, 'to_model': next_model, 'reason': reason, 'message': f'Aviso: {model_to_try} excedeu {step_timeout_sec:.0f}s. Alternando para {next_model}...'}
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(evt)
                        else:
                            progress_callback(evt)
                continue
            except Exception as err:
                latency = time.time() - t_start
                reason = f'Erro de inferencia: {err}'
                rec.record_failure(reason)
                last_error = err
                if idx + 1 < len(ladder):
                    next_model = ladder[idx + 1]
                    logger.warning(f'[ADAPTIVE-MODEL] Falha em {model_to_try}. Tentando {next_model}')
                    if progress_callback:
                        evt = {'type': 'model_degraded', 'from_model': model_to_try, 'to_model': next_model, 'reason': str(err), 'message': f'Aviso: Erro em {model_to_try}. Alternando para {next_model}...'}
                        if asyncio.iscoroutinefunction(progress_callback):
                            await progress_callback(evt)
                        else:
                            progress_callback(evt)
                continue
        raise RuntimeError(f'Todos os modelos falharam. Ultimo erro: {last_error}')

_selector_instance = None
def get_model_selector() -> AdaptiveModelSelector:
    global _selector_instance
    if _selector_instance is None:
        _selector_instance = AdaptiveModelSelector()
    return _selector_instance
