"""
THZ Minds — Agent Soul (Persistent Identity)

Inspired by soul.py (alphaXiv 2026) and PGMem (arxiv 2608.01708).
Separates volatile interaction history (MEMORY) from stable identity (SOUL).
Each agent has a SOUL.md file that persists across sessions.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentSoul:
    """Persistent identity for a debate agent.

    The soul is a markdown file that captures:
    - Core personality traits (slow-changing)
    - Speech style and disagreement patterns
    - Expertise focus areas
    - Accumulated wisdom from past debates

    Unlike memory (episodic), the soul evolves slowly and
    survives context window overflow.
    """

    def __init__(self, agent_name: str, data_dir: Path):
        self.agent_name = agent_name
        self.soul_dir = data_dir / "souls"
        self.soul_dir.mkdir(parents=True, exist_ok=True)
        self.soul_path = self.soul_dir / f"{agent_name.lower().replace(' ', '_')}.md"
        self.meta_path = self.soul_dir / f"{agent_name.lower().replace(' ', '_')}.json"

    def exists(self) -> bool:
        return self.soul_path.exists()

    def load(self) -> str:
        """Load the agent's soul (SOUL.md content)."""
        if not self.soul_path.exists():
            return ""
        return self.soul_path.read_text(encoding="utf-8")

    def save(self, soul_content: str):
        """Save or update the agent's soul."""
        self.soul_path.write_text(soul_content, encoding="utf-8")
        logger.info(f"[SOUL] Saved identity for {self.agent_name}")

    def load_meta(self) -> Dict:
        """Load soul metadata (version, last_updated, traits_hash)."""
        if not self.meta_path.exists():
            return {"version": 0, "last_updated": None, "traits": []}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def save_meta(self, meta: Dict):
        self.meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add_trait(self, trait: str, evidence: str):
        """Add or update a stable personality trait with evidence.

        Traits are the slow-changing part of identity.
        Each trait is grounded in specific debate evidence.
        """
        meta = self.load_meta()
        traits = meta.get("traits", [])

        # Check if trait already exists
        existing = next((t for t in traits if t["trait"] == trait), None)
        if existing:
            existing["evidence"].append(evidence)
            existing["count"] = existing.get("count", 1) + 1
            existing["last_seen"] = datetime.now().isoformat()
        else:
            traits.append({
                "trait": trait,
                "evidence": [evidence],
                "count": 1,
                "created": datetime.now().isoformat(),
                "last_seen": datetime.now().isoformat(),
            })

        meta["traits"] = traits
        meta["version"] = meta.get("version", 0) + 1
        meta["last_updated"] = datetime.now().isoformat()
        self.save_meta(meta)

        # Update SOUL.md with new trait summary
        self._rebuild_soul(traits)

    def get_personality_summary(self) -> str:
        """Get a concise personality summary for prompt injection.

        Returns the top traits that define this agent's behavioral style.
        """
        meta = self.load_meta()
        traits = meta.get("traits", [])
        if not traits:
            return ""

        # Sort by count (most reinforced traits first)
        sorted_traits = sorted(traits, key=lambda t: t.get("count", 0), reverse=True)
        top_traits = sorted_traits[:5]

        lines = ["Identidade acumulada de debates anteriores:"]
        for t in top_traits:
            lines.append(f"- {t['trait']} (observado {t['count']}x)")
        return "\n".join(lines)

    def _rebuild_soul(self, traits: List[Dict]):
        """Rebuild SOUL.md from accumulated traits."""
        lines = [
            f"# Soul: {self.agent_name}",
            "",
            "## Identidade",
            "",
        ]

        # Group traits by category
        strong = [t for t in traits if t.get("count", 0) >= 3]
        moderate = [t for t in traits if 1 <= t.get("count", 0) < 3]

        if strong:
            lines.append("### Traços Fortes")
            for t in strong:
                lines.append(f"- **{t['trait']}** (observado {t['count']}x)")
                if t["evidence"]:
                    lines.append(f"  - Exemplo: {t['evidence'][-1][:100]}")
            lines.append("")

        if moderate:
            lines.append("### Traços Emergentes")
            for t in moderate:
                lines.append(f"- {t['trait']} (observado {t['count']}x)")
            lines.append("")

        lines.append("---")
        lines.append(f"Última atualização: {datetime.now().isoformat()}")

        self.save("\n".join(lines))
