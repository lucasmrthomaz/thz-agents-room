"""
THZ Minds — Gerenciamento de Context Window
Auto-expand num_ctx e trunc inteligente de transcript.
"""

import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


class ContextManager:
    """Gerencia context window do LLM."""

    # Limites
    MIN_CTX = 4096
    MAX_CTX = 32768
    DEFAULT_CTX = 8192
    EXPAND_THRESHOLD = 0.70  # Expandir quando 70% cheio
    CHARS_PER_TOKEN = 4  # Aproximacao para pt-BR

    def __init__(self, num_ctx: int = DEFAULT_CTX):
        self.num_ctx = num_ctx
        self.original_ctx = num_ctx

    def estimate_tokens(self, text: str) -> int:
        """Estima quantidade de tokens em um texto."""
        return len(text) // self.CHARS_PER_TOKEN

    def estimate_prompt_tokens(
        self,
        system_prompt: str,
        knowledge_context: str,
        instruction: str,
        transcript: List[Dict]
    ) -> int:
        """Estima total de tokens do prompt."""
        total = 0
        total += self.estimate_tokens(system_prompt)
        total += self.estimate_tokens(knowledge_context)
        total += self.estimate_tokens(instruction)
        total += 100  # overhead fixo (JSON format, etc.)

        for turn in transcript:
            total += self.estimate_tokens(turn.get("content", ""))

        return total

    def auto_expand(self, estimated_tokens: int) -> int:
        """Auto-expand num_ctx se necessario."""
        # Calcular espaco disponivel
        available = self.num_ctx - estimated_tokens
        usage_ratio = estimated_tokens / self.num_ctx if self.num_ctx > 0 else 0

        if usage_ratio > self.EXPAND_THRESHOLD:
            # Calcular novo num_ctx necessario
            needed = int(estimated_tokens / self.EXPAND_THRESHOLD)
            # Arredondar para proximo multiplo de 2048
            new_ctx = ((needed // 2048) + 1) * 2048
            new_ctx = min(new_ctx, self.MAX_CTX)

            if new_ctx > self.num_ctx:
                old_ctx = self.num_ctx
                self.num_ctx = new_ctx
                logger.info(f"[CTX] Expandindo num_ctx de {old_ctx} para {self.num_ctx} "
                           f"({usage_ratio:.0%} ocupado)")
                return new_ctx

        return self.num_ctx

    def truncate_intelligently(
        self,
        history: List[Dict],
        max_tokens: int
    ) -> List[Dict]:
        """Trunc transcript de forma inteligente.

        Mantem:
        - Primeiro turno (contexto inicial)
        - Ultimos N turnos (recencia)
        Remove:
        - Turnos do meio (menos relevantes)
        """
        if not history:
            return history

        # Estimar tokens do historico atual
        total_tokens = sum(self.estimate_tokens(h.get("content", "")) for h in history)

        if total_tokens <= max_tokens:
            return history

        # Calcular quantos turnos manter
        # Manter pelo menos 3 turnos recentes + 1 inicial
        keep_recent = max(3, len(history) // 3)
        keep_initial = 1

        if len(history) <= keep_initial + keep_recent:
            return history

        # Montar transcript truncado
        truncated = []
        truncated.extend(history[:keep_initial])  # Primeiro turno
        truncated.append({
            "author": "SISTEMA",
            "content": f"[... {len(history) - keep_initial - keep_recent} argumentos anteriores omitidos ...]",
            "turn": -1
        })
        truncated.extend(history[-keep_recent:])  # Ultimos turnos

        return truncated

    def get_stats(self) -> Dict:
        """Retorna estatisticas do context manager."""
        return {
            "original_ctx": self.original_ctx,
            "current_ctx": self.num_ctx,
            "expanded": self.num_ctx > self.original_ctx,
        }
