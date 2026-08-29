"""
THZ Minds — Deteccao de Loops + Anti-Conformidade

Implements:
- Debate health analysis (diversity, trend, repetition)
- Anti-conformity from FREE-MAD (ACL 2026): agents identify flaws
  in others' outputs rather than seeking consensus
- Diversity-aware retention from DAR (arxiv 2603.20640)
"""

import logging
from typing import List, Dict, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class LoopDetector:
    """Detecta loops, analisa saude do debate, e promove anti-conformidade."""

    # Thresholds
    DIVERSITY_LOW = 0.25
    DIVERSITY_MEDIUM = 0.5
    STAGNANT_TURNS = 6
    REPETITION_LIMIT = 8
    PLAGIARISM_LIMIT = 5
    CONFORMITY_LIMIT = 3  # Max consecutive CONSENSUS before forcing disagreement

    def analyze_debate_health(self, history: List[Dict]) -> Dict:
        """Analisa saude completa do debate com anti-conformidade."""
        if len(history) < 3:
            return {
                "diversity_score": 1.0,
                "trend": "diverging",
                "repetition_count": 0,
                "plagiarism_count": 0,
                "conformity_count": 0,
                "recommendation": "continue"
            }

        diversity = self._calculate_diversity(history)
        trend = self._detect_trend(history)
        repetition_count = self._count_pattern(history, "repetition")
        plagiarism_count = self._count_pattern(history, "plagiarism")
        conformity_count = self._count_conformity(history)

        recommendation = self._determine_recommendation(
            diversity, trend, repetition_count, plagiarism_count,
            conformity_count, len(history)
        )

        return {
            "diversity_score": diversity,
            "trend": trend,
            "repetition_count": repetition_count,
            "plagiarism_count": plagiarism_count,
            "conformity_count": conformity_count,
            "recommendation": recommendation,
        }

    def _count_conformity(self, history: List[Dict]) -> int:
        """Count consecutive CONSENSUS statuses (conformity detection).

        From FREE-MAD: excessive agreement undermines debate quality.
        """
        count = 0
        for h in reversed(history):
            if h.get("status") == "CONSENSUS":
                count += 1
            else:
                break
        return count

    def get_anti_conformity_instruction(self, health: Dict, agent_role: str) -> str:
        """Generate anti-conformity instruction based on debate state.

        From FREE-MAD: agents should identify flaws in others' outputs
        rather than seeking consensus.
        """
        conformity = health.get("conformity_count", 0)
        diversity = health.get("diversity_score", 1.0)

        if conformity >= self.CONFORMITY_LIMIT:
            return (
                "\n\n⚠️ ANTI-CONFORMIDADE: Muitos agentes consecutivos concordaram. "
                "Isso pode indicar convergência prematura. "
                "Sua tarefa agora é:\n"
                "1. Identifique UM FLAW ou BURACO no argumento anterior\n"
                "2. Proponha uma ALTERNATIVA que não foi considerada\n"
                "3. Se discordar da maioria, traga DADOS concretos\n"
                "NÃO concorde automaticamente. Seja o advogado do diabo."
            )

        if diversity < self.DIVERSITY_LOW:
            return (
                "\n\n🔄 DIVERSIDADE BAIXA: O debate está muito uniforme. "
                "Para avançar, você deve trazer uma PERSPECTIVA DIFERENTE "
                "da sua área de expertise. NÃO repita o que já foi dito."
            )

        return ""

    def _calculate_diversity(self, history: List[Dict]) -> float:
        """Calcula quao diversos sao os argumentos (0.0-1.0)."""
        if len(history) < 2:
            return 1.0

        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja",
            "isso", "este", "esta", "esse", "essa", "foi", "ser", "ter", "sao",
            "estao", "pode", "devem", "fazem", "quando", "onde", "qual", "quais"
        }

        all_keywords = []
        for h in history[-8:]:
            words = set(h.get("content", "").lower().split()) - stop_words
            all_keywords.append(words)

        if not all_keywords:
            return 1.0

        all_words = set()
        for words in all_keywords:
            all_words.update(words)

        if not all_words:
            return 1.0

        similarities = []
        for i in range(len(all_keywords) - 1):
            for j in range(i + 1, len(all_keywords)):
                intersection = all_keywords[i] & all_keywords[j]
                union = all_keywords[i] | all_keywords[j]
                if union:
                    sim = len(intersection) / len(union)
                    similarities.append(sim)

        if not similarities:
            return 1.0

        avg_sim = sum(similarities) / len(similarities)
        return max(0.0, 1.0 - avg_sim)

    def _detect_trend(self, history: List[Dict]) -> str:
        """Detecta trend do debate: diverging, converging, ou stagnant."""
        if len(history) < 4:
            return "diverging"

        first_half = history[:len(history) // 2]
        second_half = history[len(history) // 2:]

        div_first = self._calculate_diversity(first_half)
        div_second = self._calculate_diversity(second_half)

        diff = div_second - div_first

        if diff > 0.1:
            return "diverging"
        elif diff < -0.1:
            return "converging"
        else:
            return "stagnant"

    def _count_pattern(self, history: List[Dict], pattern: str) -> int:
        """Conta ocorrencias de um padrao no historico."""
        if len(history) < 3:
            return 0

        count = 0
        for i in range(2, len(history)):
            prev = history[i - 1].get("content", "").lower()
            curr = history[i].get("content", "").lower()

            if prev[:100] == curr[:100] and len(prev) > 50:
                count += 1

        return count

    def _determine_recommendation(
        self,
        diversity: float,
        trend: str,
        repetition_count: int,
        plagiarism_count: int,
        conformity_count: int,
        total_turns: int
    ) -> str:
        """Determina acao recomendada com anti-conformidade."""

        # Hard limits
        if repetition_count > self.REPETITION_LIMIT:
            return "end_debate"

        if plagiarism_count > self.PLAGIARISM_LIMIT:
            return "end_debate"

        # Anti-conformity: too much agreement
        if conformity_count >= self.CONFORMITY_LIMIT:
            return "force_disagreement"

        # Repetition detected but not at limit — redirect
        if repetition_count > 3:
            return "redirect_topic"

        # Low diversity analysis
        if diversity < self.DIVERSITY_LOW:
            if trend == "stagnant":
                return "force_disagreement"
            elif trend == "converging":
                return "force_vote"

        # Long debate with medium diversity
        if total_turns > 20 and diversity < self.DIVERSITY_MEDIUM:
            return "force_vote"

        return "continue"

    def should_end_debate(self, health: Dict, current_turn: int, min_turns: int = 3) -> bool:
        """Decide se o debate deve terminar."""
        if current_turn < min_turns:
            return False

        return health.get("recommendation") in ("end_debate",)

    def should_force_action(self, health: Dict) -> Optional[str]:
        """Returns action to force if any, else None."""
        rec = health.get("recommendation", "continue")
        if rec in ("force_disagreement", "force_vote", "redirect_topic"):
            return rec
        return None


