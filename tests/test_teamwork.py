"""
Testes para o módulo de TeamWork (Engenharia, Conteúdo e Workspace Manager)
"""

import pytest
from unittest.mock import patch
from pathlib import Path
import httpx

from teamwork.models import TeamworkSessionRequest, TeamworkMode
from teamwork.workspace_manager import WorkspaceManager
from teamwork.engineering_pipeline import EngineeringPipeline
from teamwork.content_pipeline import ContentPipeline
from scenarios.scenario_engine import ScenarioEngine, get_scenario_engine

pytestmark = pytest.mark.asyncio


class TestWorkspaceManager:
    """Testes para extração e salvamento de arquivos de projeto."""

    async def test_extract_artifacts_from_markdown(self):
        sample_text = """
Aqui está a arquitetura do sistema:

### FILE: docs/ARCHITECTURE.md
```markdown
# Arquitetura do Sistema
Modelo C4 e fluxos de dados.
```

E aqui está o código principal:

### FILE: src/app.py
```python
def start_app():
    return "App rodando"
```
"""
        artifacts = WorkspaceManager.extract_artifacts_from_text(sample_text, author_role="Dev Senior")
        assert len(artifacts) == 2
        paths = [a.path for a in artifacts]
        assert "docs/ARCHITECTURE.md" in paths
        assert "src/app.py" in paths

    async def test_save_artifacts_to_disk(self, tmp_path):
        sample_text = "### FILE: config/settings.json\n```json\n{\"env\": \"prod\"}\n```"
        artifacts = WorkspaceManager.extract_artifacts_from_text(sample_text)

        project_dir = WorkspaceManager.save_artifacts("test_save_project", artifacts, base_dir=tmp_path / "output")
        assert project_dir.exists()
        target_file = project_dir / "config" / "settings.json"
        assert target_file.exists()
        assert '{"env": "prod"}' in target_file.read_text(encoding="utf-8")


class TestScenarioEngine:
    """Testes para o gerador de cenários realistas."""

    async def test_scenario_engine_returns_valid_scenario(self):
        engine = get_scenario_engine()
        sc = engine.get_random_engineering_scenario()
        assert sc.title is not None
        assert len(sc.constraints) >= 2
        assert len(sc.tech_stack) >= 2

        formatted = engine.format_scenario_prompt(sc)
        assert "CENÁRIO DE ENGENHARIA" in formatted
        assert "Restrições de Produção" in formatted

    async def test_scenario_engine_returns_content_topic(self):
        engine = get_scenario_engine()
        topic = engine.get_random_content_topic()
        assert isinstance(topic, str)
        assert len(topic) > 10


class TestTeamworkPipelines:
    """Testes para execução das pipelines de engenharia e conteúdo."""

    async def test_engineering_pipeline_execution(self, tmp_path):
        pipeline = EngineeringPipeline(model="qwen2.5:7b")
        req = TeamworkSessionRequest(
            goal="Criar microsserviço de cache distribuído com Redis e FastAPI",
            mode=TeamworkMode.ENGINEERING,
            auto_heal=False
        )

        mock_resp = {
            "message": {
                "content": (
                    "### FILE: src/cache_service.py\n```python\nclass Cache:\n    pass\n```\n"
                    "### FILE: Dockerfile\n```dockerfile\nFROM python:3.11-slim\n```"
                )
            }
        }
        response_obj = httpx.Response(
            200,
            json=mock_resp,
            request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
        )

        with patch.object(httpx.AsyncClient, "post", return_value=response_obj):
            result = await pipeline.run(req)
            assert result.status == "success"
            assert result.total_steps == 7
            assert len(result.artifacts) >= 2

    async def test_content_pipeline_execution(self, tmp_path):
        pipeline = ContentPipeline(model="qwen2.5:7b")
        req = TeamworkSessionRequest(
            goal="Guia completo de migração de monólito para microsserviços",
            mode=TeamworkMode.CONTENT
        )

        mock_resp = {
            "message": {
                "content": (
                    "### FILE: ARTIGO_FINAL.md\n```markdown\n# Guia de Migração\nConteúdo completo...\n```\n"
                    "### FILE: metadata.json\n```json\n{\"tags\": [\"arquitetura\", \"devops\"]}\n```"
                )
            }
        }
        response_obj = httpx.Response(
            200,
            json=mock_resp,
            request=httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
        )

        with patch.object(httpx.AsyncClient, "post", return_value=response_obj):
            result = await pipeline.run(req)
            assert result.status == "success"
            assert result.total_steps == 6
            assert len(result.artifacts) >= 2
