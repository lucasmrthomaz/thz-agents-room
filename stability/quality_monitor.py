"""
THZ Minds — Monitor de Qualidade
Verifica qualidade dos argumentos e injeta feedback no prompt.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class QualityMonitor:
    """Monitora qualidade dos argumentos e fornece feedback."""

    MIN_WORDS = 50
    MAX_NOVELTY_THRESHOLD = 0.3

    def monitor_argument_quality(
        self,
        argument: str,
        history: List[Dict],
        agent_role: str
    ) -> Dict:
        """Analisa qualidade de um argumento."""
        word_count = len(argument.split())
        references_previous = self._references_previous(argument, history)
        novelty_score = self._calculate_novelty(argument, history)
        expertise_alignment = self._check_expertise_alignment(argument, agent_role)

        return {
            "word_count": word_count,
            "is_too_short": word_count < self.MIN_WORDS,
            "references_previous": references_previous,
            "novelty_score": novelty_score,
            "expertise_alignment": expertise_alignment,
            "overall_quality": self._overall_score(
                word_count, references_previous, novelty_score, expertise_alignment
            ),
        }

    def inject_quality_feedback(
        self,
        health: Dict,
        agent_role: str,
        instruction: str,
        quality: Dict = None
    ) -> str:
        """Injeta feedback de qualidade no instruction."""
        extra_instructions = []

        # Feedback baseado na saude do debate
        diversity = health.get("diversity_score", 1.0)
        if diversity < 0.4:
            extra_instructions.append(
                "IMPORTANTE: Traga um angulo NOVO e DIFERENTE. NAO repita argumentos ja apresentados."
            )

        # Feedback baseado na qualidade do argumento
        if quality:
            if quality.get("is_too_short"):
                extra_instructions.append(
                    f"Sua resposta esta muito curta ({quality['word_count']} palavras). "
                    "Desenvolva mais o argumento com dados especificos."
                )

            if quality.get("novelty_score", 1.0) < 0.3:
                extra_instructions.append(
                    "Seu argumento e muito similar aos anteriores. "
                    "Use sua expertise de " + agent_role + " para trazer dados e perspectivas unicas."
                )

            if not quality.get("references_previous", False):
                extra_instructions.append(
                    "Referencie explicitamente um argumento anterior para manter a coesao do debate."
                )

        # Feedback baseado na role
        role_feedback = self._get_role_specific_feedback(agent_role, health)
        if role_feedback:
            extra_instructions.append(role_feedback)

        if extra_instructions:
            instruction += "\n" + "\n".join(extra_instructions)

        return instruction

    def _references_previous(self, argument: str, history: List[Dict]) -> bool:
        """Verifica se o argumento referencia um anterior."""
        if not history:
            return True

        arg_lower = argument.lower()

        # Verificar mencao a agentes anteriores
        agent_names = ["arquiteto", "sre", "devops", "dba", "security", "po", "scrum master", "gerente"]
        for name in agent_names:
            if name in arg_lower:
                return True

        # Verificar mencao a conceitos anteriores
        keywords = ["concordo", "discordo", "embora", "porém", "entretanto", "alem disso",
                    "complementando", "refutando", "contrariando", "analisando"]
        for kw in keywords:
            if kw in arg_lower:
                return True

        return False

    def _calculate_novelty(self, argument: str, history: List[Dict]) -> float:
        """Calcula quao novo e o argumento (0.0-1.0)."""
        if not history:
            return 1.0

        arg_words = set(argument.lower().split())
        # Remover stop words
        stop_words = {"o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
                      "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja"}
        arg_words -= stop_words

        if not arg_words:
            return 0.5

        # Verificar overlap com historico
        overlaps = []
        for h in history[-5:]:
            hist_words = set(h.get("content", "").lower().split()) - stop_words
            if hist_words:
                intersection = arg_words & hist_words
                union = arg_words | hist_words
                overlap = len(intersection) / len(union) if union else 0
                overlaps.append(overlap)

        if not overlaps:
            return 1.0

        avg_overlap = sum(overlaps) / len(overlaps)
        return max(0.0, 1.0 - avg_overlap)

    def _check_expertise_alignment(self, argument: str, agent_role: str) -> float:
        """Verifica se o argumento esta alinhado com a expertise do agente."""
        role_keywords = {
            "Software Architect": ["arquitetura", "design", "padrao", "simplicidade", "complexidade",
                                   "KISS", "YAGNI", "manutenivel", "escalavel"],
            "Site Reliability Engineer": ["tolerancia", "falha", "disponibilidade", "SLA", "SLO",
                                          "monitoramento", "observabilidade", "SPOF"],
            "DevOps Engineer": ["CI/CD", "pipeline", "deploy", "container", "docker", "kubernetes",
                               "automacao", "infraestrutura"],
            "Database Specialist": ["banco", "dados", "query", "index", "normalizacao", "transacao",
                                   "ACID", "NoSQL", "relacional"],
            "Security Specialist": ["seguranca", "vulnerabilidade", "autenticacao", "autorizacao",
                                   "criptografia", "injecao", "XSS", "CSRF"],
            "Product Owner": ["valor", "negocio", "ROI", "prioridade", "usuario", "cliente",
                             "requisito", "backlog"],
            "Scrum Master": ["processo", "sprint", "impedimento", "fluxo", "time", "cerimonia",
                            "retrospectiva"],
            "Project Manager": ["prazo", "recurso", "risco", "orcamento", "timeline", "escopo",
                               "stakeholder"],
        }

        keywords = role_keywords.get(agent_role, [])
        if not keywords:
            return 0.5

        arg_lower = argument.lower()
        matches = sum(1 for kw in keywords if kw.lower() in arg_lower)
        alignment = min(1.0, matches / max(3, len(keywords) // 2))

        return alignment

    def _overall_score(
        self,
        word_count: int,
        references_previous: bool,
        novelty_score: float,
        expertise_alignment: float
    ) -> float:
        """Calcula score geral de qualidade."""
        score = 0.0

        # Word count (max 0.25)
        if word_count >= 100:
            score += 0.25
        elif word_count >= 50:
            score += 0.15
        else:
            score += 0.05

        # References previous (0.15)
        if references_previous:
            score += 0.15

        # Novelty (max 0.35)
        score += novelty_score * 0.35

        # Expertise alignment (max 0.25)
        score += expertise_alignment * 0.25

        return min(1.0, score)

    def _get_role_specific_feedback(self, agent_role: str, health: Dict) -> str:
        """Retorna feedback especifico para a role do agente."""
        diversity = health.get("diversity_score", 1.0)

        if diversity < 0.4:
            role_tips = {
                "Software Architect": "Foque em padroes arquiteturais que outros nao mencionaram.",
                "Site Reliability Engineer": "Analise impacto em tolerancia a falhas que ainda nao foi coberto.",
                "DevOps Engineer": "Traga dados de pipelines e automacao reais.",
                "Database Specialist": "Apresente metricas de performance de queries.",
                "Security Specialist": "Identifique vulnerabilidades nao mencionadas.",
                "Product Owner": "Analise ROI e valor para o usuario final.",
                "Scrum Master": "Identifique impedimentos de processo nao discutidos.",
                "Project Manager": "Apresente impacto em prazo e recursos.",
            }
            return role_tips.get(agent_role, "")

        return ""
