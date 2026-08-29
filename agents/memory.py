"""
THZ Minds — Agent Memory (Episodic + Semantic)

Implements the write-manage-read loop from "Memory for Autonomous LLM Agents"
(arxiv 2603.07670). Each agent has:
- Episodic memory: specific debate events (topic, outcome, argument)
- Semantic memory: generalized traits abstracted from episodes
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentMemory:
    """Episodic and semantic memory for a debate agent.

    Episodic: "I debated microserviços on 2026-08-27 and argued for monolito"
    Semantic: "I tend to favor simplicity in architecture decisions"
    """

    def __init__(self, agent_name: str, data_dir: Path):
        self.agent_name = agent_name
        self.memory_dir = data_dir / "memories"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        safe_name = agent_name.lower().replace(" ", "_")
        self.episodic_path = self.memory_dir / f"{safe_name}_episodic.jsonl"
        self.semantic_path = self.memory_dir / f"{safe_name}_semantic.json"

    # ── Episodic Memory ──────────────────────────────────────────

    def record_episode(
        self,
        topic: str,
        outcome: str,
        my_argument: str,
        turn: int,
        consensus: bool = False,
    ):
        """Record a specific debate episode."""
        episode = {
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "outcome": outcome,
            "argument_preview": my_argument[:300],
            "turn": turn,
            "consensus": consensus,
        }

        with open(self.episodic_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")

        logger.debug(f"[MEMORY] Recorded episode for {self.agent_name}: {topic[:50]}")

    def get_recent_episodes(self, limit: int = 10) -> List[Dict]:
        """Get the most recent episodes."""
        if not self.episodic_path.exists():
            return []

        episodes = []
        with open(self.episodic_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        episodes.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return episodes[-limit:]

    def get_relevant_episodes(self, topic: str, limit: int = 3) -> List[Dict]:
        """Get episodes relevant to a topic (keyword matching).

        For production, this could use embeddings for semantic search.
        """
        all_episodes = self.get_recent_episodes(limit=50)
        if not all_episodes:
            return []

        # Simple keyword relevance
        topic_words = set(topic.lower().split())
        scored = []
        for ep in all_episodes:
            ep_words = set(ep.get("topic", "").lower().split())
            overlap = len(topic_words & ep_words)
            scored.append((overlap, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    # ── Semantic Memory ──────────────────────────────────────────

    def update_semantic(self):
        """Consolidate episodic memories into semantic traits.

        This is called periodically to abstract stable patterns
        from accumulated episodes.
        """
        episodes = self.get_recent_episodes(limit=30)
        if len(episodes) < 3:
            return  # Not enough data

        # Analyze patterns
        topics = [ep.get("topic", "") for ep in episodes]
        consensus_count = sum(1 for ep in episodes if ep.get("consensus"))
        total = len(episodes)

        # Extract topic preferences
        topic_words = {}
        for t in topics:
            for word in t.lower().split():
                if len(word) > 4:  # Skip short words
                    topic_words[word] = topic_words.get(word, 0) + 1

        top_topics = sorted(topic_words.items(), key=lambda x: x[1], reverse=True)[:5]

        semantic = {
            "agent": self.agent_name,
            "updated": datetime.now().isoformat(),
            "total_episodes": total,
            "consensus_rate": consensus_count / max(1, total),
            "preferred_topics": [t[0] for t in top_topics],
            "argument_style": self._infer_style(episodes),
        }

        self.semantic_path.write_text(
            json.dumps(semantic, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"[MEMORY] Updated semantic memory for {self.agent_name}")

    def get_semantic_summary(self) -> str:
        """Get a summary of semantic memory for prompt injection."""
        if not self.semantic_path.exists():
            return ""

        semantic = json.loads(self.semantic_path.read_text(encoding="utf-8"))
        lines = [
            f"Perfil acumulado de {self.agent_name}:",
            f"- Taxa de consenso: {semantic.get('consensus_rate', 0):.0%}",
            f"- Tópicos preferidos: {', '.join(semantic.get('preferred_topics', [])[:3])}",
            f"- Estilo: {semantic.get('argument_style', 'analítico')}",
        ]
        return "\n".join(lines)

    def _infer_style(self, episodes: List[Dict]) -> str:
        """Infer argument style from episode history."""
        # Simple heuristic based on argument previews
        technical_terms = 0
        for ep in episodes:
            preview = ep.get("argument_preview", "").lower()
            technical_terms += sum(
                1 for word in ["sistema", "arquitetura", "perform", "escalab",
                               "seguranç", "deploy", "código", "test"]
                if word in preview
            )

        if technical_terms > len(episodes) * 2:
            return "técnico e detalhado"
        elif technical_terms > len(episodes):
            return "equilibrado"
        else:
            return "conceitual e estratégico"
