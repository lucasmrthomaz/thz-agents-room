"""
Testes de integracao para o WebSocket e servidor do THz Room
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestWebSocketIntegration:
    """Testes de integracao para o WebSocket."""

    async def test_websocket_autonomous_mode(self):
        """Testa que o modo autonomous aceita payload valido."""
        from server import AutonomousSessionRequest

        # Valida payload
        payload = AutonomousSessionRequest(
            mode="autonomous",
            duration_hours=0.5,
            num_ctx=4096,
            model="qwen2.5:7b"
        )

        assert payload.mode == "autonomous"
        assert payload.duration_hours == 0.5
        assert payload.num_ctx == 4096
        assert payload.model == "qwen2.5:7b"


class TestGracefulShutdown:
    """Testes para o GracefulShutdown."""

    def test_initial_state(self):
        """Testa estado inicial do shutdown manager."""
        from server import GracefulShutdown

        manager = GracefulShutdown()
        assert manager.should_exit is False
        assert manager.current_session is None

    def test_signal_handler_sets_flag(self):
        """Testa que o signal handler define should_exit."""
        from server import GracefulShutdown

        manager = GracefulShutdown()
        manager._signal_handler(None, None)
        assert manager.should_exit is True

    async def test_save_current_state_no_session(self):
        """Testa save_current_state quando nao ha sessao ativa."""
        from server import GracefulShutdown

        manager = GracefulShutdown()
        manager.current_session = None

        # Nao deve lancar erro
        await manager.save_current_state()


class TestModelResolution:
    """Testes para resolucao de modelo."""

    async def test_resolve_model_requested(self):
        """Testa que modelo solicitado e retornado."""
        from server import resolve_model

        model = await resolve_model("qwen2.5:7b")
        assert model == "qwen2.5:7b"

    async def test_resolve_model_env(self):
        """Testa que variavel de ambiente e usada."""
        from server import resolve_model

        with patch.dict('os.environ', {'OLLAMA_MODEL': 'llama3.2:3b'}):
            model = await resolve_model(None)
            assert model == "llama3.2:3b"

    async def test_resolve_model_fallback(self):
        """Testa fallback para default quando Ollama falha."""
        from server import resolve_model, DEFAULT_MODEL

        with patch.dict('os.environ', {}, clear=True):
            with patch('server.httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__ = AsyncMock(side_effect=Exception("Connection refused"))
                mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

                model = await resolve_model(None)
                assert model == DEFAULT_MODEL


class TestAgentCreation:
    """Testes para criacao de agentes."""

    def test_create_agents_count(self):
        """Testa que 9 agentes sao criados."""
        from server import create_agents

        agents = create_agents("qwen2.5:7b")
        assert len(agents) == 9

    def test_create_agents_names(self):
        """Testa nomes dos agentes."""
        from server import create_agents

        agents = create_agents("qwen2.5:7b")
        names = [a.name for a in agents]

        expected = ["Arquiteto", "SRE", "DevOps", "DBA", "Security", "PO", "Scrum Master", "Gerente", "Dev Senior"]
        assert names == expected

    def test_create_agents_model(self):
        """Testa que todos os agentes usam o mesmo modelo."""
        from server import create_agents

        agents = create_agents("qwen2.5:7b")
        for agent in agents:
            assert agent.model == "qwen2.5:7b"

    def test_create_agents_system_prompt_contains_respect_rules(self):
        """Testa que system prompt contem regras de respeito."""
        from server import create_agents

        agents = create_agents("qwen2.5:7b")
        for agent in agents:
            assert "REGRAS RIGOROSAS" in agent.system_prompt
            assert "Portugues do Brasil" in agent.system_prompt
            assert "CONTINUE" in agent.system_prompt

    def test_create_agents_different_roles(self):
        """Testa que cada agente tem papel diferente."""
        from server import create_agents

        agents = create_agents("qwen2.5:7b")
        roles = [a.role_title for a in agents]

        # Todos os papeis devem ser unicos
        assert len(roles) == len(set(roles))
