"""
THZ Minds — Modelos de Dados para o Módulo de TeamWork
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class TeamworkMode(str, Enum):
    ENGINEERING = "engineering"
    CONTENT = "content"


class TeamworkRole(str, Enum):
    # Engenharia de Software
    TECH_LEAD = "Tech Lead"
    ARCHITECT = "Arquiteto"
    DBA = "DBA Specialist"
    SENIOR_DEV = "Dev Senior"
    DEVOPS_SRE = "DevOps & SRE"
    SECURITY = "Security Specialist"
    QA_TESTER = "QA Tester"

    # Conteúdo & Artigos
    RESEARCHER = "Pesquisador"
    TECHNICAL_WRITER = "Redator Técnico"
    TECHNICAL_REVIEWER = "Revisor Técnico (SME)"
    SEO_SPECIALIST = "Especialista SEO"
    GRAMMAR_REVIEWER = "Revisor Gramatical"
    EDITOR_IN_CHIEF = "Editor-Chefe"


class TeamworkStage(str, Enum):
    INIT = "init"
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    DATA_MODELING = "data_modeling"
    IMPLEMENTATION = "implementation"
    INFRASTRUCTURE = "infrastructure"
    SECURITY_AUDIT = "security_audit"
    TESTING = "testing"
    SELF_HEALING = "self_healing"
    EDITORIAL_RESEARCH = "editorial_research"
    FIRST_DRAFT = "first_draft"
    TECHNICAL_REVIEW = "technical_review"
    SEO_OPTIMIZATION = "seo_optimization"
    GRAMMAR_POLISH = "grammar_polish"
    FINAL_PACKAGING = "final_packaging"
    COMPLETED = "completed"
    FAILED = "failed"


class TeamworkArtifact(BaseModel):
    path: str = Field(description="Caminho relativo do arquivo (ex: 'src/auth.py', 'schema.sql', 'README.md')")
    content: str = Field(description="Conteúdo textual completo do arquivo.")
    file_type: Literal["code", "sql", "yaml", "markdown", "json", "config"] = Field(default="code")
    author_role: str = Field(description="Papel do agente que gerou o arquivo.")
    created_at: Optional[str] = None


class TeamworkStepResult(BaseModel):
    step_number: int
    stage: TeamworkStage
    agent_name: str
    role_title: str
    reasoning: Optional[str] = None
    contribution: str = Field(description="Explicação ou artefato produzido pelo agente nesta etapa.")
    artifacts: List[TeamworkArtifact] = Field(default_factory=list)
    success: bool = True
    error: Optional[str] = None


class TeamworkSessionRequest(BaseModel):
    mode: TeamworkMode = Field(default=TeamworkMode.ENGINEERING, description="'engineering' ou 'content'")
    goal: str = Field(description="Objetivo detalhado da solução ou tema do artigo a ser produzido.")
    project_name: Optional[str] = Field(default=None, description="Nome do projeto / pasta de saída.")
    model: Optional[str] = Field(default=None, description="Modelo Ollama a utilizar.")
    num_ctx: int = Field(default=8192, ge=4096, le=32768)
    auto_heal: bool = Field(default=True, description="Executa auto-correção via sandbox caso testes falhem.")


class TeamworkSessionResult(BaseModel):
    session_id: str
    mode: TeamworkMode
    goal: str
    project_name: str
    status: Literal["success", "partial", "failed"]
    total_steps: int
    steps: List[TeamworkStepResult] = Field(default_factory=list)
    artifacts: List[TeamworkArtifact] = Field(default_factory=list)
    output_directory: Optional[str] = None
    executive_summary: str = ""
    created_at: str
