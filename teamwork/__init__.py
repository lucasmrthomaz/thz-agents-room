"""
THZ Minds — Módulo de TeamWork Autônomo
Orquestra pipelines de trabalho colaborativo entre múltiplos agentes especialistas
para entrega de soluções reais de engenharia de software e artigos técnicos.
"""

from .models import (
    TeamworkMode,
    TeamworkStage,
    TeamworkRole,
    TeamworkArtifact,
    TeamworkSessionRequest,
    TeamworkSessionResult,
)
from .workspace_manager import WorkspaceManager
from .engineering_pipeline import EngineeringPipeline
from .content_pipeline import ContentPipeline

__all__ = [
    "TeamworkMode",
    "TeamworkStage",
    "TeamworkRole",
    "TeamworkArtifact",
    "TeamworkSessionRequest",
    "TeamworkSessionResult",
    "WorkspaceManager",
    "EngineeringPipeline",
    "ContentPipeline",
]
