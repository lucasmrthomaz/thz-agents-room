"""
Testes para os endpoints compatíveis com OpenAI API (/v1)
"""

import pytest
from unittest.mock import patch
import httpx
from httpx import AsyncClient, ASGITransport

from server import app
from teamwork.models import TeamworkSessionResult, TeamworkMode, TeamworkArtifact

pytestmark = pytest.mark.asyncio


class TestOpenAICompatibleAPI:
    """Testes para conformidade com o protocolo OpenAI (/v1/models, /v1/chat/completions)."""

    async def test_list_models_includes_virtual_teamwork_models(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/models")
            assert resp.status_code == 200
            data = resp.json()
            assert data["object"] == "list"
            model_ids = [m["id"] for m in data["data"]]
            assert "thz-teamwork:engineering" in model_ids
            assert "thz-teamwork:content" in model_ids
            assert "thz-council:debate" in model_ids
            assert "thz-lang:copilot" in model_ids

    async def test_chat_completions_blocks_out_of_scope_topic(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "model": "thz-teamwork:engineering",
                "messages": [
                    {"role": "user", "content": "Quero comprar um carro com motor v8 e piscina de luxo"}
                ]
            }
            resp = await client.post("/v1/chat/completions", json=payload)
            assert resp.status_code == 400
            data = resp.json()
            assert "guardrail" in data["detail"].lower()

    async def test_chat_completions_engineering_pipeline(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "model": "thz-teamwork:engineering",
                "messages": [
                    {"role": "user", "content": "Criar microsserviço de autenticação JWT com FastAPI e PostgreSQL"}
                ],
                "stream": False
            }

            mock_result = TeamworkSessionResult(
                session_id="test_session_123",
                mode=TeamworkMode.ENGINEERING,
                goal="Criar microsserviço de autenticação JWT com FastAPI e PostgreSQL",
                project_name="test_project",
                status="success",
                total_steps=7,
                artifacts=[
                    TeamworkArtifact(path="src/main.py", content="print('Auth Service')", file_type="code", author_role="Dev Senior"),
                    TeamworkArtifact(path="requirements.txt", content="fastapi\nuvicorn", file_type="config", author_role="Dev Senior")
                ],
                output_directory="output/test_project",
                executive_summary="Projeto gerado com sucesso.",
                created_at="2026-08-27T18:00:00"
            )

            from teamwork.engineering_pipeline import EngineeringPipeline

            with patch.object(EngineeringPipeline, "run", return_value=mock_result):
                resp = await client.post("/v1/chat/completions", json=payload)
                assert resp.status_code == 200
                data = resp.json()
                assert data["object"] == "chat.completion"
                assert len(data["choices"]) > 0
                content = data["choices"][0]["message"]["content"]
                assert "Solução de Engenharia" in content or "Arquivos" in content
