"""
THZ Minds — Dynamic Speaker Selection

Implements bidding-based speaker selection from:
- "Who Speaks Next?" (Frontiers 2025) - adjacency pairs + self-selection
- LLMCR (GitHub 2026) - decentralized bidding orchestrator
- "Consilience" (arxiv 2608.20564) - adaptive communication control

Instead of fixed round-robin, agents bid for the right to speak
based on relevance, expertise, and desire to contribute.
"""

import json
import logging
import random
from typing import Dict, List, Optional, Tuple

import httpx

from config import settings as cfg

logger = logging.getLogger(__name__)

OLLAMA_CHAT_URL = cfg.OLLAMA_CHAT_URL


class SpeakerSelector:
    """Dynamically selects which agents speak next.

    Three mechanisms:
    1. Self-selection: Agents bid based on relevance
    2. Current-speaker-selects-next: Last speaker can designate
    3. Force-pick: If all bids are low, pick most relevant

    This creates natural conversation flow where:
    - Not everyone speaks every round (2-4 of 9)
    - Relevant experts are prioritized
    - Silence is a valid choice
    """

    def __init__(self, model: str, ollama_url: str = OLLAMA_CHAT_URL):
        self.model = model
        self.ollama_url = ollama_url
        self.speaking_history: Dict[str, int] = {}  # agent -> turns since last spoke
        self.question_queue: List[Dict] = []  # Pending questions between agents

    async def select_next_speakers(
        self,
        agents: List,
        history: List[Dict],
        current_turn: int,
        max_speakers: int = 3,
        pending_questions: Optional[List[Dict]] = None,
    ) -> List[str]:
        """Select 1-3 agents to speak next.

        Priority:
        1. Agents with pending questions (must respond)
        2. Highest bidders (relevant to current discussion)
        3. Agents who haven't spoken recently
        """
        if not agents:
            return []

        # Update speaking recency
        if history:
            last_speaker = history[-1]["author"]
            for name in self.speaking_history:
                self.speaking_history[name] = self.speaking_history.get(name, 0) + 1
            self.speaking_history[last_speaker] = 0

        selected = []

        # 1. Check for pending questions (must respond)
        if pending_questions:
            for q in pending_questions:
                if q["to"] in [a.name for a in agents] and q["to"] not in selected:
                    selected.append(q["to"])
                    if len(selected) >= max_speakers:
                        return selected

        # 2. Collect bids from remaining agents
        candidates = [a for a in agents if a.name not in selected]
        bids = {}

        for agent in candidates:
            bid = await self._calculate_bid(
                agent, history, current_turn
            )
            bids[agent.name] = bid

        # 3. Sort by bid (highest first)
        sorted_bids = sorted(bids.items(), key=lambda x: x[1], reverse=True)

        # 4. Select top candidates
        for name, bid in sorted_bids:
            if len(selected) >= max_speakers:
                break
            if bid >= 3:  # Minimum threshold
                selected.append(name)

        # 5. Force-pick if no one bid high enough
        if not selected and candidates:
            # Pick agent who spoke least recently
            least_recent = min(
                candidates,
                key=lambda a: self.speaking_history.get(a.name, 999),
            )
            selected.append(least_recent.name)
            logger.info(
                f"[SPEAKER] Force-picked {least_recent.name} (no high bids)"
            )

        # 6. Add diversity: if all selected are same type, add different one
        if len(selected) >= 2:
            selected_types = set()
            for name in selected:
                agent = next((a for a in agents if a.name == name), None)
                if agent:
                    selected_types.add(agent.role_title)

            if len(selected_types) == 1:
                # All same type, try to add different
                for agent in candidates:
                    if (
                        agent.name not in selected
                        and agent.role_title not in selected_types
                    ):
                        selected.append(agent.name)
                        break

        logger.info(
            f"[SPEAKER] Turno {current_turn}: selecionados {selected} "
            f"(bids: {bids})"
        )
        return selected[:max_speakers]

    async def _calculate_bid(self, agent, history: List[Dict], current_turn: int) -> int:
        """Calculate how relevant it is for this agent to speak now.

        Bid is 1-10:
        - 1-3: Not relevant, agent should stay quiet
        - 4-6: Moderately relevant
        - 7-10: Highly relevant, should definitely speak

        Factors:
        - Relevance of last argument to agent's expertise
        - Time since agent last spoke
        - Whether agent was directly addressed
        """
        if not history:
            return 8  # First turn, everyone should bid high

        last_arg = history[-1]
        last_content = last_arg.get("content", "").lower()

        # Factor 1: Expertise relevance (0-4 points)
        expertise_keywords = {
            "Software Architect": [
                "arquitetura", "design", "padrão", "KISS", "YAGNI",
                "monolito", "microserviço", "escala", "complexidade",
            ],
            "Site Reliability Engineer": [
                "tolerância", "falha", "SPOF", "disponibilidade", "SLA",
                "monitoramento", "observabilidade", "resiliência",
            ],
            "DevOps Engineer": [
                "CI/CD", "pipeline", "deploy", "docker", "kubernetes",
                "container", "infraestrutura", "automação",
            ],
            "Database Specialist": [
                "banco", "dados", "query", "index", "SQL", "NoSQL",
                "normalização", "transação", "performance",
            ],
            "Security Specialist": [
                "segurança", "vulnerabilidade", "autenticação", "JWT",
                "injeção", "XSS", "CSRF", "criptografia",
            ],
            "Product Owner": [
                "negócio", "ROI", "valor", "usuário", "requisito",
                "prioridade", "backlog", "produto",
            ],
            "Scrum Master": [
                "processo", "sprint", "impedimento", "fluxo",
                "retrospectiva", "cerimônia", "time",
            ],
            "Project Manager": [
                "prazo", "recurso", "risco", "orçamento", "timeline",
                "escopo", "stakeholder",
            ],
            "Senior Developer": [
                "código", "testes", "SOLID", "design pattern",
                "refatoração", "code smell", "clean code",
            ],
        }

        keywords = expertise_keywords.get(agent.role_title, [])
        expertise_score = 0
        for kw in keywords:
            if kw.lower() in last_content:
                expertise_score += 1
        expertise_score = min(4, expertise_score)

        # Factor 2: Time since last spoke (0-3 points)
        turns_since = self.speaking_history.get(agent.name, 999)
        recency_score = min(3, turns_since // 2)

        # Factor 3: Direct address (0-3 points)
        agent_name_lower = agent.name.lower()
        address_score = 0
        if agent_name_lower in last_content:
            address_score = 3
        elif any(word in last_content for word in ["pergunto", "questiono", "discordo"]):
            address_score = 1

        total = expertise_score + recency_score + address_score

        # Add some randomness (±1) to prevent deterministic patterns
        total = max(1, min(10, total + random.randint(-1, 1)))

        return total

    def add_question(self, from_agent: str, to_agent: str, question: str):
        """Add a pending question to the queue."""
        self.question_queue.append({
            "from": from_agent,
            "to": to_agent,
            "question": question,
        })

    def get_pending_questions(self, for_agent: str) -> Optional[Dict]:
        """Get pending question for a specific agent."""
        for q in self.question_queue:
            if q["to"] == for_agent:
                return q
        return None

    def clear_answered_question(self, to_agent: str):
        """Remove answered question from queue."""
        self.question_queue = [
            q for q in self.question_queue if q["to"] != to_agent
        ]

    def reset(self):
        """Reset state for new debate."""
        self.speaking_history = {}
        self.question_queue = []
