"""
THZ Minds — Deteccao de Loops
Analise de saude do debate e deteccao de espirais de repeticao.
"""

import logging
from typing import List, Dict
from collections import Counter

logger = logging.getLogger(__name__)


class LoopDetector:
    """Detecta loops e analisa saude do debate."""

    # Thresholds (reduzidos para ser menos agressivo)
    DIVERSITY_LOW = 0.25
    DIVERSITY_MEDIUM = 0.5
    STAGNANT_TURNS = 6
    REPETITION_LIMIT = 8
    PLAGIARISM_LIMIT = 5

    def analyze_debate_health(self, history: List[Dict]) -> Dict:
        """Analisa saude completa do debate."""
        if len(history) < 3:
            return {
                "diversity_score": 1.0,
                "trend": "diverging",
                "repetition_count": 0,
                "plagiarism_count": 0,
                "recommendation": "continue"
            }

        # Calcular diversity score
        diversity = self._calculate_diversity(history)

        # Detectar trend
        trend = self._detect_trend(history)

        # Contar repeticoes e plagios (baseado em headers de log)
        repetition_count = self._count_pattern(history, "repetition")
        plagiarism_count = self._count_pattern(history, "plagiarism")

        # Determinar recomendacao
        recommendation = self._determine_recommendation(
            diversity, trend, repetition_count, plagiarism_count, len(history)
        )

        return {
            "diversity_score": diversity,
            "trend": trend,
            "repetition_count": repetition_count,
            "plagiarism_count": plagiarism_count,
            "recommendation": recommendation,
        }

    def _calculate_diversity(self, history: List[Dict]) -> float:
        """Calcula quao diversos sao os argumentos (0.0-1.0)."""
        if len(history) < 2:
            return 1.0

        # Extrair palavras-chave de cada argumento (excluindo stop words)
        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja",
            "isso", "este", "esta", "esse", "essa", "foi", "ser", "ter", "sao",
            "estao", "pode", "devem", "fazem", "quando", "onde", "qual", "quais"
        }

        all_keywords = []
        for h in history[-8:]:  # Ultimos 8 argumentos
            words = set(h.get("content", "").lower().split()) - stop_words
            all_keywords.append(words)

        if not all_keywords:
            return 1.0

        # Calcular intersecao media
        all_words = set()
        for words in all_keywords:
            all_words.update(words)

        if not all_words:
            return 1.0

        # Para cada par de argumentos, calcular similaridade
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

        # Diversity = 1 - media de similaridade
        avg_sim = sum(similarities) / len(similarities)
        return max(0.0, 1.0 - avg_sim)

    def _detect_trend(self, history: List[Dict]) -> str:
        """Detecta trend do debate: diverging, converging, ou stagnant."""
        if len(history) < 4:
            return "diverging"

        # Comparar diversity dos primeiros vs ultimos turnos
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
        """Conta ocorrencias de um padrao no historico.
        NOTA: Contagem aproximada baseada em variacao de conteudo."""
        if len(history) < 3:
            return 0

        count = 0
        for i in range(2, len(history)):
            # Verificar se argumento atual e muito similar ao anterior
            prev = history[i - 1].get("content", "").lower()
            curr = history[i].get("content", "").lower()

            # Similaridade simplificada (primeiras 100 chars)
            if prev[:100] == curr[:100] and len(prev) > 50:
                count += 1

        return count

    def _determine_recommendation(
        self,
        diversity: float,
        trend: str,
        repetition_count: int,
        plagiarism_count: int,
        total_turns: int
    ) -> str:
        """Determina acao recomendada."""
        # Limites absolutos
        if repetition_count > self.REPETITION_LIMIT:
            return "end_debate"

        if plagiarism_count > self.PLAGIARISM_LIMIT:
            return "end_debate"

        # Analise de diversidade
        if diversity < self.DIVERSITY_LOW:
            if trend == "stagnant":
                return "force_consensus"
            elif trend == "converging":
                return "force_consensus"

        # Debates longos com baixa diversidade
        if total_turns > 20 and diversity < self.DIVERSITY_MEDIUM:
            return "force_consensus"

        return "continue"

    def should_end_debate(self, health: Dict, current_turn: int, min_turns: int = 3) -> bool:
        """Decide se o debate deve terminar."""
        if current_turn < min_turns:
            return False

        return health.get("recommendation") in ("end_debate", "force_consensus")
