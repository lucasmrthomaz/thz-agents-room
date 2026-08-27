"""
Fixtures compartilhadas para testes do THz Room
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Configura para usar asyncio no pytest
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """Cria um event loop compartilhado para todos os testes."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def temp_db(tmp_path):
    """Cria um banco de dados temporario para testes."""
    db_path = tmp_path / "test_cortex.db"

    # Patch do DB_PATH antes de importar o server
    import sys
    if 'server' in sys.modules:
        del sys.modules['server']

    with patch('server.DB_PATH', db_path):
        from server import CortexDB
        await CortexDB.init()
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()


@pytest.fixture
def sample_topic():
    """Topico de exemplo para testes."""
    return "Kafka vs RabbitMQ para fila de eventos com 10k msgs/s"


@pytest.fixture
def sample_agent_decision():
    """Decisao de agente de exemplo."""
    return {
        "argument": "Kafka e mais adequado para alta volumetria devido a sua arquitetura distribuida.",
        "status": "CONTINUE"
    }


@pytest.fixture
def sample_transcript():
    """Transcript de exemplo."""
    return [
        {"author": "Arquiteto", "content": "Argumento do arquiteto", "turn": 1},
        {"author": "SRE", "content": "Argumento do SRE", "turn": 2},
        {"author": "DevOps", "content": "Argumento do DevOps", "turn": 3},
    ]


@pytest.fixture
def session_dir(tmp_path):
    """Diretorio de sessao temporario."""
    return tmp_path / "sessions" / "2026-01-01" / "12-00" / "test-session"


@pytest_asyncio.fixture
async def mock_ollama_response():
    """Mock de resposta do Ollama."""
    return {
        "message": {
            "content": json.dumps({"topic": "Kafka vs RabbitMQ"})
        }
    }
