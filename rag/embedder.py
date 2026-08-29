"""
THZ Minds — Gerenciamento de Embeddings
Gera embeddings vetoriais para argumentos do debate.
Gracefully degrades quando modelo nao esta disponivel.
"""

import struct
import logging
import time
import httpx
from typing import List, Optional, Dict
from collections import OrderedDict

from config import settings as cfg

logger = logging.getLogger(__name__)

OLLAMA_EMBED_URL = cfg.OLLAMA_EMBED_URL
DEFAULT_MODEL = cfg.EMBEDDING_MODEL
EMBEDDING_DIM = cfg.EMBEDDING_DIM


class Embedder:
    """Gerencia embeddings via Ollama com cache e rate limiting."""

    def __init__(self, model: str = DEFAULT_MODEL, cache_size: int = 500):
        self.model = model
        self.dim = EMBEDDING_DIM
        self.available = None  # None = nao checado, True/False = checado
        
        # Cache LRU de embeddings (text -> embedding)
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self._cache_size = cache_size
        
        # Rate limiting
        self._last_call_time: float = 0
        self._min_interval: float = 0.5  # Minimo 500ms entre chamadas

    async def check_availability(self) -> bool:
        """Verifica se o modelo de embeddings esta disponivel."""
        if self.available is not None:
            return self.available

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": self.model, "input": "teste"},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    self.available = True
                    logger.info(f"[EMBED] Modelo {self.model} disponivel")
                else:
                    self.available = False
                    logger.warning(f"[EMBED] Modelo {self.model} nao disponivel (HTTP {resp.status_code})")
        except Exception as e:
            self.available = False
            logger.warning(f"[EMBED] Modelo {self.model} nao disponivel: {e}")

        return self.available

    async def embed(self, text: str) -> Optional[List[float]]:
        """Gera embedding de um texto. Retorna None se indisponivel.
        Usa cache LRU e rate limiting para evitar chamadas excessivas."""
        if self.available is False:
            return None

        # Verificar cache primeiro
        cache_key = text[:500]  # Usar primeiros 500 chars como chave
        if cache_key in self._cache:
            # Mover para o final (mais recente)
            self._cache.move_to_end(cache_key)
            return self._cache[cache_key]

        # Rate limiting: esperar minimo entre chamadas
        now = time.monotonic()
        time_since_last = now - self._last_call_time
        if time_since_last < self._min_interval:
            await self._async_sleep(self._min_interval - time_since_last)

        self._last_call_time = time.monotonic()

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": self.model, "input": text},
                    timeout=30.0
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    self.available = True
                    embedding = embeddings[0]
                    
                    # Adicionar ao cache LRU
                    if len(self._cache) >= self._cache_size:
                        self._cache.popitem(last=False)  # Remover mais antigo
                    self._cache[cache_key] = embedding
                    
                    return embedding
                return None
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    self.available = False
                    logger.debug(f"[EMBED] Modelo {self.model} nao encontrado (404)")
                else:
                    logger.error(f"[EMBED] Erro HTTP: {e}")
                return None
            except Exception as e:
                logger.error(f"[EMBED] Erro ao gerar embedding: {e}")
                return None

    @staticmethod
    async def _async_sleep(seconds: float):
        """Sleep assíncrono."""
        import asyncio
        await asyncio.sleep(seconds)

    async def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[Optional[List[float]]]:
        """Gera embeddings de varios textos em batch."""
        if self.available is False:
            return [None] * len(texts)

        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = []
            for text in batch:
                emb = await self.embed(text)
                batch_results.append(emb)
            results.extend(batch_results)
        return results

    @staticmethod
    def to_blob(embedding: List[float]) -> bytes:
        """Converte embedding para BLOB (float32 little-endian)."""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def from_blob(blob: bytes) -> List[float]:
        """Converte BLOB para embedding."""
        n = len(blob) // 4
        return list(struct.unpack(f"{n}f", blob))

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calcula similaridade cosseno entre dois vetores."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
