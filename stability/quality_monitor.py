"""
THZ Minds — Monitor de Qualidade + Diversity-Aware Retention

Implements:
- Argument quality monitoring (word count, novelty, expertise alignment)
- Diversity-Aware Retention from DAR (arxiv 2603.20640): select only
  the most divergent responses for broadcast
- Improved novelty detection with bigram analysis
- Concrete data bonus (numbers, metrics, specific tools)
"""

import logging
from typing import Dict, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class QualityMonitor:
    """Monitora qualidade dos argumentos e seleciona respostas diversas."""

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
        has_concrete_data = self._has_concrete_data(argument)

        return {
            "word_count": word_count,
            "is_too_short": word_count < self.MIN_WORDS,
            "references_previous": references_previous,
            "novelty_score": novelty_score,
            "expertise_alignment": expertise_alignment,
            "has_concrete_data": has_concrete_data,
            "overall_quality": self._overall_score(
                word_count, references_previous, novelty_score,
                expertise_alignment, has_concrete_data
            ),
        }

    def select_diverse_responses(
        self,
        history: List[Dict],
        max_to_broadcast: int = 3,
    ) -> List[Dict]:
        """Select only the most divergent responses for broadcast.

        From DAR (arxiv 2603.20640): instead of passing ALL arguments,
        select the subset that maximally disagrees with each other.

        Returns max_to_broadcast arguments that represent:
        1. The last argument (always include for response)
        2. The most different argument from the last
        3. A minority opinion (if exists)
        """
        if len(history) <= max_to_broadcast:
            return list(history)

        # 1. Always include last argument
        selected = [history[-1]]
        selected_indices = {len(history) - 1}

        # 2. Find most different from last (keyword-based)
        last_words = set(history[-1]["content"].lower().split())
        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja",
        }
        last_content_words = last_words - stop_words

        best_diff_idx = 0
        best_diff_score = -1

        for i, h in enumerate(history[:-1]):
            if i in selected_indices:
                continue
            their_words = set(h["content"].lower().split()) - stop_words
            if not their_words or not last_content_words:
                continue

            # Jaccard distance (1 - similarity)
            intersection = last_content_words & their_words
            union = last_content_words | their_words
            similarity = len(intersection) / len(union) if union else 0
            diff_score = 1.0 - similarity

            if diff_score > best_diff_score:
                best_diff_score = diff_score
                best_diff_idx = i

        if best_diff_idx not in selected_indices:
            selected.append(history[best_diff_idx])
            selected_indices.add(best_diff_idx)

        # 3. Find minority opinion (agent who disagreed most)
        if len(history) > 3:
            minority_idx = self._find_minority_cluster(history, selected_indices)
            if minority_idx is not None:
                selected.append(history[minority_idx])
                selected_indices.add(minority_idx)

        return selected[:max_to_broadcast]

    def _find_minority_cluster(
        self, history: List[Dict], exclude_indices: set
    ) -> Optional[int]:
        """Find an argument that represents a minority viewpoint."""
        # Simple heuristic: find argument with most unique keywords
        if len(history) < 4:
            return None

        stop_words = {
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja",
        }

        # Count keyword frequency across all arguments
        keyword_freq = Counter()
        arg_keywords = []
        for h in history:
            words = set(h["content"].lower().split()) - stop_words
            arg_keywords.append(words)
            keyword_freq.update(words)

        # Find argument with most rare keywords (minority viewpoint)
        best_idx = None
        best_rarity = -1

        for i, kw_set in enumerate(arg_keywords):
            if i in exclude_indices:
                continue
            if not kw_set:
                continue
            # Rarity = inverse frequency
            rarity = sum(1 / max(1, keyword_freq[k]) for k in kw_set)
            rarity_per_word = rarity / len(kw_set) if kw_set else 0

            if rarity_per_word > best_rarity:
                best_rarity = rarity_per_word
                best_idx = i

        return best_idx

    def _has_concrete_data(self, argument: str) -> bool:
        """Check if argument contains concrete data (numbers, tools, metrics)."""
        import re

        # Check for numbers (metrics, percentages, sizes)
        has_numbers = bool(re.search(r'\d+[%xkKmM]|\$\d+|~\d+', argument))

        # Check for specific tool/framework names
        specific_terms = [
            "postgres", "mysql", "redis", "kafka", "docker", "kubernetes",
            "terraform", "prometheus", "grafana", "nginx", "react", "fastapi",
            "pydantic", "sqlalchemy", "celery", "rabbitmq", "elasticsearch",
        ]
        has_specific = any(term in argument.lower() for term in specific_terms)

        return has_numbers or has_specific

    def inject_quality_feedback(
        self,
        health: Dict,
        agent_role: str,
        instruction: str,
        quality: Dict = None
    ) -> str:
        """Injeta feedback de qualidade no instruction."""
        extra_instructions = []

        diversity = health.get("diversity_score", 1.0)
        if diversity < 0.4:
            extra_instructions.append(
                "IMPORTANTE: Traga um angulo NOVO e DIFERENTE. NAO repita argumentos ja apresentados."
            )

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

            if not quality.get("has_concrete_data", False):
                extra_instructions.append(
                    "Traga dados CONCRETOS: numeros, nomes de ferramentas, metricas, limites reais."
                )

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

        agent_names = ["arquiteto", "sre", "devops", "dba", "security", "po", "scrum master", "gerente"]
        for name in agent_names:
            if name in arg_lower:
                return True

        keywords = ["concordo", "discordo", "embora", "porém", "entretanto", "alem disso",
                    "complementando", "refutando", "contrariando", "analisando"]
        for kw in keywords:
            if kw in arg_lower:
                return True

        return False

    def _calculate_novelty(self, argument: str, history: List[Dict]) -> float:
        """Calcula quao novo e o argumento (0.0-1.0).

        Improved with bigram analysis (not just unigrams).
        """
        if not history:
            return 1.0

        stop_words = {"o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
                      "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja"}

        # Unigram novelty
        arg_words = set(argument.lower().split()) - stop_words
        if not arg_words:
            return 0.5

        # Bigram novelty (catches phrase-level repetition)
        arg_bigrams = self._get_bigrams(argument.lower()) - stop_words

        overlaps = []
        for h in history[-5:]:
            hist_words = set(h.get("content", "").lower().split()) - stop_words
            hist_bigrams = self._get_bigrams(h.get("content", "").lower())

            if hist_words:
                # Unigram overlap
                intersection = arg_words & hist_words
                union = arg_words | hist_words
                uni_overlap = len(intersection) / len(union) if union else 0

                # Bigram overlap (weighted higher)
                bi_intersection = len(arg_bigrams & hist_bigrams)
                bi_union = len(arg_bigrams | hist_bigrams) if arg_bigrams or hist_bigrams else 1
                bi_overlap = bi_intersection / bi_union

                # Combined: 60% unigram + 40% bigram
                combined = 0.6 * uni_overlap + 0.4 * bi_overlap
                overlaps.append(combined)

        if not overlaps:
            return 1.0

        avg_overlap = sum(overlaps) / len(overlaps)
        return max(0.0, 1.0 - avg_overlap)

    def _get_bigrams(self, text: str) -> set:
        """Extract bigrams from text."""
        words = text.split()
        return {f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)}

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
            "Senior Developer": ["codigo", "testes", "SOLID", "design pattern", "refatoracao",
                                "code smell", "clean code"],
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
        expertise_alignment: float,
        has_concrete_data: bool = False,
    ) -> float:
        """Calcula score geral de qualidade."""
        score = 0.0

        # Word count (max 0.20)
        if word_count >= 100:
            score += 0.20
        elif word_count >= 50:
            score += 0.12
        else:
            score += 0.03

        # References previous (0.10)
        if references_previous:
            score += 0.10

        # Novelty (max 0.30)
        score += novelty_score * 0.30

        # Expertise alignment (max 0.20)
        score += expertise_alignment * 0.20

        # Concrete data bonus (0.20)
        if has_concrete_data:
            score += 0.20

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
                "Senior Developer": "Aponte code smells ou violacoes de SOLID nao mencionadas.",
            }
            return role_tips.get(agent_role, "")

        return ""
