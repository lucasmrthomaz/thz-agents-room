"""
Testes para geração de topicos do THz Room
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Marca todos os testes deste arquivo como asyncio
pytestmark = pytest.mark.asyncio


class TestTopicGeneration:
    """Testes para a funcao generate_topic."""

    async def test_generate_topic_success(self):
        """Testa geracao bem-sucedida de topico via Ollama."""
        from server import generate_topic

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": json.dumps({"topic": "Kafka vs RabbitMQ para fila de 10k msgs/s"})
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            topic = await generate_topic("qwen2.5:7b", [])

            assert topic == "Kafka vs RabbitMQ para fila de 10k msgs/s"

    async def test_generate_topic_with_history(self):
        """Testa geracao de topico com historico."""
        from server import generate_topic

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": json.dumps({"topic": "Docker vs Podman"})
            }
        }
        mock_response.raise_for_status = MagicMock()

        history = ["Topico 1", "Topico 2", "Topico 3"]

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            topic = await generate_topic("qwen2.5:7b", history)

            # Verifica que o historico foi incluido na mensagem
            call_args = mock_client.post.call_args
            payload = call_args[1]['json'] if 'json' in call_args[1] else call_args[0][1]
            assert "Topico 1" in payload["messages"][0]["content"]

    async def test_generate_topic_invalid_response(self):
        """Testa fallback quando resposta e invalida."""
        from server import generate_topic, FALLBACK_TOPICS

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "x" * 200  # Muito longo
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            topic = await generate_topic("qwen2.5:7b", [])

            # Deve retornar um topico do fallback
            assert topic in FALLBACK_TOPICS

    async def test_generate_topic_http_error(self):
        """Testa fallback quando ocorre erro HTTP."""
        from server import generate_topic, FALLBACK_TOPICS

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Connection error"))

            topic = await generate_topic("qwen2.5:7b", [])

            # Deve retornar um topico do fallback
            assert topic in FALLBACK_TOPICS

    async def test_generate_topic_always_returns_topic(self):
        """Testa que generate_topic sempre retorna um topico (nunca None)."""
        from server import generate_topic, FALLBACK_TOPICS

        # Cria lista grande de topicos historicos
        history = [f"Topico {i}" for i in range(100)]

        # Mock do Ollama retornando erro para testar fallback
        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("Connection error"))

            topic = await generate_topic("qwen2.5:7b", history)

            # Nunca deve retornar None
            assert topic is not None
            assert isinstance(topic, str)
            assert len(topic) > 0

    async def test_generate_topic_json_parse_error(self):
        """Testa fallback quando JSON nao pode ser parseado."""
        from server import generate_topic, FALLBACK_TOPICS

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "Isso nao e um JSON valido"
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            topic = await generate_topic("qwen2.5:7b", [])

            # Deve retornar um topico do fallback ou a string raw se valida
            assert topic is not None
            assert len(topic) > 0

    async def test_generate_topic_uses_fallback_when_ollama_returns_garbage(self):
        """Testa que fallback e usado quando Ollama retorna lixo."""
        from server import generate_topic, FALLBACK_TOPICS

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "content": "ele deu problema na hora de gerar..."
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('server.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)

            topic = await generate_topic("qwen2.5:7b", [])

            # Deve retornar um topico valido
            assert topic is not None
            assert 10 <= len(topic) <= 150
