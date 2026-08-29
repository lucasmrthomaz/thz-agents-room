"""
THZ Minds — Meta-Moderator

Implements the meta-cognitive moderation framework from
"Meta-Moderator: Empowering Multi-Agent Debate with Meta-Cognition"
(arxiv 2608.23029).

The Meta-Moderator performs three functions:
1. Monitoring: Is the debate making substantive progress?
2. Control: Should we continue or finalize?
3. Adjudication: Synthesize a final answer from the debate.
"""

import json
import logging
from typing import Dict, List, Optional

import httpx

from config import settings as cfg

logger = logging.getLogger(__name__)

OLLAMA_CHAT_URL = cfg.OLLAMA_CHAT_URL


class MetaModerator:
    """Meta-cognitive moderator that decides when to stop and how to synthesize.

    Unlike the reactive LoopDetector, the Meta-Moderator is proactive:
    - Measures substantive progress (not just diversity)
    - Detects when new information stops appearing
    - Forces voting when deliberation stagnates
    - Synthesizes final answer from debate trajectory
    """

    def __init__(self, model: str, ollama_url: str = OLLAMA_CHAT_URL):
        self.model = model
        self.ollama_url = ollama_url
        self.deliberation_budget = 20  # Max turns before forced decision
        self.progress_history: List[float] = []

    async def should_continue(
        self,
        history: List[Dict],
        health: Dict,
        current_turn: int,
    ) -> Dict:
        """Decide whether debate should continue.

        Returns:
            {
                "action": "continue" | "finalize" | "force_vote",
                "reason": str,
                "confidence": float
            }
        """
        # 1. Budget check
        if current_turn >= self.deliberation_budget:
            return {
                "action": "finalize",
                "reason": "Orçamento de deliberação excedido",
                "confidence": 1.0,
            }

        # 2. Measure substantive progress
        progress = await self._measure_progress(history)
        self.progress_history.append(progress["score"])

        # 3. Check for information plateau
        if len(self.progress_history) >= 4:
            recent = self.progress_history[-4:]
            if max(recent) - min(recent) < 0.1:
                # No progress in last 4 measurements
                if current_turn >= 6:
                    return {
                        "action": "force_vote",
                        "reason": "Deliberação estagnada — forçar votação",
                        "confidence": 0.8,
                    }

        # 4. Low diversity + converging trend
        diversity = health.get("diversity_score", 1.0)
        trend = health.get("trend", "diverging")

        if diversity < 0.3 and trend == "converging" and current_turn >= 6:
            return {
                "action": "force_vote",
                "reason": "Baixa diversidade e convergência — votar",
                "confidence": 0.7,
            }

        # 5. Check repetition count
        repetition = health.get("repetition_count", 0)
        if repetition > 3 and current_turn >= 6:
            return {
                "action": "force_vote",
                "reason": f"{repetition} repetições detectadas — forçar decisão",
                "confidence": 0.85,
            }

        return {
            "action": "continue",
            "reason": "Deliberação produtiva",
            "confidence": 0.6,
        }

    async def synthesize_final(
        self,
        history: List[Dict],
        topic: str,
    ) -> str:
        """Synthesize final answer from debate trajectory.

        This is the adjudication function: weigh competing rationales
        and identify unresolved inconsistencies before committing.
        """
        # Build debate trajectory
        trajectory = []
        for h in history:
            trajectory.append(
                f"[{h['author']} - Turno {h['turn']}]: {h['content'][:200]}"
            )

        trajectory_text = "\n".join(trajectory)

        prompt = (
            "Você é um moderador que sintetiza debates técnicos.\n\n"
            "Dado o debate abaixo sobre '{topic}', gere uma síntese FINAL em português:\n\n"
            "## Resumo Executivo\n"
            "1-2 frases sobre o que foi discutido\n\n"
            "## Pontos de Acordo (com quórum)\n"
            "- Lista dos pontos onde há consenso (maioria dos participantes)\n\n"
            "## Pontos de Discordância\n"
            "- Lista dos pontos onde não houve acordo, com argumentos de cada lado\n\n"
            "## Decisão Recomendada\n"
            "- Recomendação técnica com justificativa\n\n"
            "## Ações Práticas\n"
            "- 3-5 ações específicas e acionáveis\n\n"
            "Regras:\n"
            "- Seja OBJETIVO e DIRETO\n"
            "- NÃO repita argumentos — sintetize\n"
            "- Identifique QUAL agente defendeu cada posição\n"
            "- Se houver empate, presente ambos os lados\n\n"
            f"Topic: {topic}\n\n"
            f"Debate:\n{trajectory_text}\n\n"
            "Síntese:"
        )

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_ctx": 4096},
                }
                resp = await client.post(
                    self.ollama_url, json=payload, timeout=90.0
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"].strip()

        except Exception as e:
            logger.error(f"[MODERATOR] Erro ao sintetizar: {e}")
            return self._fallback_synthesis(history, topic)

    async def _measure_progress(self, history: List[Dict]) -> Dict:
        """Measure how much substantive progress the debate is making.

        Progress = new information being introduced vs repetition.
        """
        if len(history) < 3:
            return {"score": 1.0, "new_info": True}

        # Compare last 3 arguments with previous ones
        recent = [h["content"].lower() for h in history[-3:]]
        previous = [h["content"].lower() for h in history[:-3]]

        if not previous:
            return {"score": 1.0, "new_info": True}

        # Check for new keywords
        recent_words = set()
        for r in recent:
            recent_words.update(r.split())

        previous_words = set()
        for p in previous:
            previous_words.update(p.split())

        # New words = words in recent that weren't in previous
        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "não", "mais", "como", "também", "já",
        }
        recent_content = recent_words - stop_words
        previous_content = previous_words - stop_words

        if not recent_content:
            return {"score": 0.0, "new_info": False}

        new_ratio = len(recent_content - previous_content) / len(recent_content)
        return {"score": new_ratio, "new_info": new_ratio > 0.2}

    def _fallback_synthesis(self, history: List[Dict], topic: str) -> str:
        """Simple fallback synthesis without LLM."""
        if not history:
            return f"Nenhum debate registrado sobre '{topic}'."

        agents = list(set(h["author"] for h in history))
        last_args = [h["content"][:100] for h in history[-3:]]

        return (
            f"Debate sobre '{topic}' com {len(history)} turnos.\n"
            f"Participantes: {', '.join(agents)}.\n"
            f"Últimos argumentos:\n" +
            "\n".join(f"- {a}" for a in last_args)
        )

    def reset(self):
        """Reset moderator state for new debate."""
        self.progress_history = []
