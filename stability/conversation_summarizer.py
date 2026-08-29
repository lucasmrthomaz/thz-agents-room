"""
THZ Minds — Conversation Summarizer

Implements summary-based communication from "Scaling LLM-Driven MAS"
(arxiv 2607.27942, Principle P4): agents share concise natural-language
summaries, not full transcripts.

This prevents:
- Echo and plagiarism (agents don't read full arguments)
- Context bloat (saves tokens)
- Error propagation (summary filters out noise)
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional

import httpx

from config import settings as cfg

logger = logging.getLogger(__name__)

OLLAMA_CHAT_URL = cfg.OLLAMA_CHAT_URL


class ConversationSummarizer:
    """Generates concise discussion summaries at regular intervals.

    Instead of passing full transcripts, this module creates structured
    summaries that capture:
    - Key points of agreement/disagreement
    - Who said what (without full text)
    - Status of each topic (resolved/open)
    """

    SUMMARY_MODEL = "qwen3.5:9b"

    def __init__(self, model: str, ollama_url: str = OLLAMA_CHAT_URL, summary_model: str = None):
        self.model = model
        self.summary_model = summary_model or self.SUMMARY_MODEL
        self.ollama_url = ollama_url
        self.last_summary_turn = 0
        self.cached_summary = ""
        self.consensus_points: List[str] = []
        self.open_disagreements: List[str] = []

    async def get_or_create_summary(
        self,
        history: List[Dict],
        current_turn: int,
        interval: int = 3,
    ) -> str:
        """Get cached summary or create new one if interval elapsed."""
        if current_turn - self.last_summary_turn < interval and self.cached_summary:
            return self.cached_summary

        if len(history) < 2:
            return "Início da discussão. Aguardando argumentos."

        summary = await self._generate_summary(history)
        self.cached_summary = summary
        self.last_summary_turn = current_turn
        return summary

    def get_last_argument_context(self, history: List[Dict]) -> str:
        """Get just the last argument for direct response context.

        This is the minimal context needed for a meaningful response.
        """
        if not history:
            return "Nenhum argumento ainda."

        last = history[-1]
        return (
            f"Último argumento de {last['author']} (Turno {last['turn']}):\n"
            f"{last['content']}"
        )

    def get_consensus_points(self) -> List[str]:
        """Return points already in consensus."""
        return self.consensus_points

    def get_open_disagreements(self) -> List[str]:
        """Return points still in disagreement."""
        return self.open_disagreements

    async def _generate_summary(self, history: List[Dict]) -> str:
        """Generate a structured summary using LLM."""
        # Build compact transcript (just key info)
        compact = []
        for h in history[-12:]:  # Last 12 turns max
            compact.append(
                f"[{h['author']} - Turno {h['turn']}]: "
                f"{h['content'][:150]}..."
            )

        transcript_text = "\n".join(compact)

        prompt = (
            "Você é um moderador que resume debates técnicos.\n\n"
            "Dado o transcript abaixo, gere um resumo ESTRUTURADO em português:\n\n"
            "## Resumo da Discussão\n"
            "- 3 a 5 bullets points com os principais argumentos\n"
            "- Indique o status de cada ponto: [consenso] ou [discordância]\n\n"
            "## Pontos de Consenso\n"
            "- Lista dos pontos onde há acordo\n\n"
            "## Discordâncias Abertas\n"
            "- Lista dos pontos onde ainda há divergência\n\n"
            "Regras:\n"
            "- Seja CONCISO (máx 200 palavras total)\n"
            "- NÃO copie frases do transcript\n"
            "- Identifique QUEM disse o quê (1 palavra)\n"
            "- Foque no QUE foi dito, não no COMO foi dito\n\n"
            f"Transcript:\n{transcript_text}\n\n"
            "Resumo:"
        )

        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "model": self.summary_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_ctx": 2048},
                }
                resp = await client.post(
                    self.ollama_url, json=payload, timeout=90.0
                )
                resp.raise_for_status()
                raw = resp.json()["message"]["content"].strip()

                # Parse consensus and disagreements
                self._parse_summary(raw)
                return raw

        except Exception as e:
            logger.error(f"[SUMMARY] Erro ao gerar resumo (model={self.summary_model}): {e}")
            return self._fallback_summary(history)

    def _parse_summary(self, summary: str):
        """Extract consensus points and disagreements from summary text."""
        self.consensus_points = []
        self.open_disagreements = []

        lines = summary.split("\n")
        section = None
        for line in lines:
            line_lower = line.lower().strip()
            if "consenso" in line_lower or "acordo" in line_lower:
                section = "consensus"
            elif "discordância" in line_lower or "divergência" in line_lower:
                section = "disagreement"
            elif line.startswith("- ") or line.startswith("* "):
                point = line[2:].strip()
                if section == "consensus":
                    self.consensus_points.append(point)
                elif section == "disagreement":
                    self.open_disagreements.append(point)

    def _fallback_summary(self, history: List[Dict]) -> str:
        """Generate simple fallback summary without LLM."""
        if not history:
            return "Discussão iniciada."

        agents = list(set(h["author"] for h in history))
        total_turns = len(history)

        # Simple keyword extraction
        all_words = " ".join(h["content"] for h in history[-6:]).lower().split()
        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "não", "mais", "como", "também", "já", "isso",
        }
        keywords = [w for w in all_words if len(w) > 4 and w not in stop_words]
        top_keywords = list(set(keywords))[:5]

        return (
            f"Discussão com {total_turns} turnos entre {', '.join(agents)}.\n"
            f"Temas principais: {', '.join(top_keywords)}.\n"
            f"Último autor: {history[-1]['author']}."
        )
