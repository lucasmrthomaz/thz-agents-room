"""
Testes para as funcionalidades de evolucao do THZ Minds (Fases 1 a 12)
"""

import json
import pytest
from pathlib import Path
import aiosqlite

from server import (
    ActionType,
    AgentDecision,
    calculate_vote_weight,
    requires_human_approval,
    CortexDB,
)
from stability.loop_detector import LoopDetector
from tools.registry import (
    ToolRegistry,
    WebSearchTool,
    DBQueryTool,
    FileReadTool,
    CodeExecuteTool,
    ToolPermission,
)
from export.report_generator import ReportGenerator

pytestmark = pytest.mark.asyncio


class TestAgentDecisionEvolution:
    """Testes para o novo modelo AgentDecision com campos de raciocinio, pergunta e tool_call."""

    async def test_agent_decision_with_reasoning_and_question(self):
        decision = AgentDecision(
            argument="Precisamos avaliar a latencia da replicacao.",
            status="CONTINUE",
            question_to="DBA",
            reasoning="O DBA mencionou Postgres assincrono, preciso saber o lag aceitavel."
        )
        assert decision.status == "CONTINUE"
        assert decision.question_to == "DBA"
        assert "lag aceitavel" in decision.reasoning
        assert decision.tool_call is None

    async def test_agent_decision_with_tool_call(self):
        decision = AgentDecision(
            argument="Consultando documentacao do Kubernetes.",
            status="CONTINUE",
            tool_call={
                "tool": "file_read",
                "params": {"file_path": "README.md"}
            }
        )
        assert decision.tool_call["tool"] == "file_read"
        assert decision.tool_call["params"]["file_path"] == "README.md"


class TestZeroTrustAndPermissions:
    """Testes para o controle Zero-Trust de acoes dos agentes."""

    async def test_requires_human_approval_dangerous(self):
        assert await requires_human_approval(ActionType.DANGEROUS) is True

    async def test_requires_human_approval_read_only(self):
        assert await requires_human_approval(ActionType.READ_ONLY) is False

    async def test_requires_human_approval_write_db(self):
        assert await requires_human_approval(ActionType.WRITE_DB) is False

    async def test_requires_human_approval_consensus_threshold(self):
        # Abaixo de 3 discussoes: nao requer
        assert await requires_human_approval(ActionType.CONSENSUS, {"times_discussed": 2}) is False
        # Acima de 3 discussoes: requer aprovacao
        assert await requires_human_approval(ActionType.CONSENSUS, {"times_discussed": 4}) is True


class TestVoteWeighting:
    """Testes para calculo de peso de voto baseado em skills."""

    async def test_vote_weight_with_high_expertise(self):
        skills = {
            "DBA": [
                {"skill_domain": "PostgreSQL", "expertise_level": 0.9},
                {"skill_domain": "Query Optimization", "expertise_level": 0.8},
            ]
        }
        weight = await calculate_vote_weight("DBA", skills)
        assert 0.8 < weight <= 1.0

    async def test_vote_weight_default(self):
        weight = await calculate_vote_weight("Desconhecido", {})
        assert weight == 0.5


class TestLoopDetectorEvolution:
    """Testes para thresholds atualizados do LoopDetector."""

    async def test_loop_detector_thresholds(self):
        detector = LoopDetector()
        assert detector.DIVERSITY_LOW == 0.25
        assert detector.REPETITION_LIMIT == 8
        assert detector.PLAGIARISM_LIMIT == 5


class TestToolRegistry:
    """Testes para o registro e execucao segura de ferramentas."""

    async def test_registry_registration_and_list(self):
        registry = ToolRegistry()
        tools = registry.list_tools()
        assert len(tools) >= 4
        names = [t["name"] for t in tools]
        assert "web_search" in names
        assert "db_query" in names
        assert "file_read" in names
        assert "code_execute" in names

    async def test_file_read_safe(self, tmp_path):
        tool = FileReadTool()
        result = await tool.execute(file_path="README.md", max_chars=100)
        assert result.success is True
        assert len(result.result) > 0

    async def test_file_read_traversal_blocked(self):
        tool = FileReadTool()
        result = await tool.execute(file_path="../../windows/system32/cmd.exe")
        assert result.success is False

    async def test_code_execute_safe_math(self):
        tool = CodeExecuteTool()
        result = await tool.execute(code="print(10 * 5 + 2)")
        assert result.success is True
        assert result.result == "52"

    async def test_code_execute_blocks_forbidden_imports(self):
        tool = CodeExecuteTool()
        result = await tool.execute(code="import os\nos.system('dir')")
        assert result.success is False

    async def test_tool_registry_execute(self):
        registry = ToolRegistry()
        result = await registry.execute_call({"tool": "code_execute", "params": {"code": "print(2 ** 8)"}})
        assert result.success is True
        assert result.result == "256"

    async def test_tool_registry_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute_call({"tool": "non_existent_tool"})
        assert result.success is False


class TestReportGenerator:
    """Testes para o gerador de relatorios de debates."""

    async def test_report_generator_formats(self, tmp_path):
        db_file = tmp_path / "test_cortex.db"
        async with aiosqlite.connect(db_file) as db:
            await db.execute("""
                CREATE TABLE conversations (
                    id TEXT PRIMARY KEY,
                    topic TEXT,
                    session_id TEXT,
                    summary_short TEXT,
                    summary_full TEXT,
                    created_at TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    agent_name TEXT,
                    content TEXT,
                    status TEXT,
                    turn INTEGER,
                    created_at TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE argument_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    turn INTEGER,
                    agent_name TEXT,
                    quality_score REAL,
                    novelty_score REAL,
                    expertise_alignment REAL,
                    overall_score REAL
                )
            """)
            await db.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?)",
                ("conv_test_123", "Microsservicos vs Monolito", "sess_001", "Resumo curto.", "Resumo completo.", "2026-08-27 12:00:00")
            )
            await db.execute(
                "INSERT INTO messages (conversation_id, agent_name, content, status, turn, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("conv_test_123", "Arquiteto", "Monolito modular e melhor para equipes pequenas.", "CONTINUE", 1, "2026-08-27 12:01:00")
            )
            await db.execute(
                "INSERT INTO messages (conversation_id, agent_name, content, status, turn, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("conv_test_123", "DevOps", "Concordo plenamente.", "CONSENSUS", 2, "2026-08-27 12:02:00")
            )
            await db.commit()

        generator = ReportGenerator(db_path=db_file)

        # Markdown
        md = await generator.generate_markdown("conv_test_123")
        assert "Microsservicos vs Monolito" in md
        assert "Arquiteto" in md
        assert "DevOps" in md

        # JSON
        json_str = await generator.generate_json("conv_test_123")
        json_data = json.loads(json_str)
        assert json_data["topic"] == "Microsservicos vs Monolito"
        assert json_data["total_turns"] == 2

        # HTML
        html_doc = await generator.generate_html("conv_test_123")
        assert "<!DOCTYPE html>" in html_doc
        assert "Microsservicos vs Monolito" in html_doc
