"""THZ Minds — Agent Identity & Memory Layer.

Provides persistent identity (SOUL) and episodic/semantic memory
for each debate agent across sessions.
"""

from .soul import AgentSoul
from .memory import AgentMemory

__all__ = ["AgentSoul", "AgentMemory"]
