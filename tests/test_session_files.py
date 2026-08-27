"""
Testes para a classe SessionFiles do THz Room
"""

import json
from pathlib import Path

import pytest
import pytest_asyncio

# Marca todos os testes deste arquivo como asyncio
pytestmark = pytest.mark.asyncio


class TestSessionFiles:
    """Testes para gerenciamento de arquivos de sessao."""

    async def test_get_session_dir(self, tmp_path):
        """Testa criacao do diretorio de sessao."""
        from server import SessionFiles

        session_id = "2026-01-01_12-00"

        with patch('server.SESSIONS_DIR', tmp_path / "sessions"):
            session_dir = SessionFiles.get_session_dir(session_id)

            # Verifica estrutura de diretorios
            assert session_dir.exists()
            assert session_id in str(session_dir)

    async def test_save_debate(self, tmp_path):
        """Testa salvamento de debate."""
        from server import SessionFiles

        session_dir = tmp_path / "test_session"
        session_dir.mkdir(parents=True, exist_ok=True)

        transcript = [
            {"author": "Arquiteto", "content": "Argumento 1", "turn": 1},
            {"author": "SRE", "content": "Argumento 2", "turn": 2},
        ]

        await SessionFiles.save_debate(
            session_dir,
            debate_num=1,
            topic="Kafka vs RabbitMQ",
            transcript=transcript,
            summary_short="Resumo curto do debate",
            summary_full="Resumo completo do debate com contexto situacional"
        )

        # Verifica se arquivos foram criados
        debate_dir = session_dir / "debate_001"
        assert debate_dir.exists()
        assert (debate_dir / "metadata.json").exists()
        assert (debate_dir / "transcript.json").exists()
        assert (debate_dir / "summary.json").exists()

        # Verifica conteudo do metadata
        with open(debate_dir / "metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)
            assert metadata["debate_num"] == 1
            assert metadata["topic"] == "Kafka vs RabbitMQ"
            assert metadata["total_turns"] == 2
            assert "Arquiteto" in metadata["agents"]
            assert "SRE" in metadata["agents"]

        # Verifica conteudo do transcript
        with open(debate_dir / "transcript.json", "r", encoding="utf-8") as f:
            saved_transcript = json.load(f)
            assert len(saved_transcript) == 2
            assert saved_transcript[0]["author"] == "Arquiteto"

        # Verifica conteudo do summary
        with open(debate_dir / "summary.json", "r", encoding="utf-8") as f:
            summary = json.load(f)
            assert summary["summary_short"] == "Resumo curto do debate"
            assert summary["summary_full"] == "Resumo completo do debate com contexto situacional"

    async def test_save_debate_without_summary(self, tmp_path):
        """Testa salvamento de debate sem resumo."""
        from server import SessionFiles

        session_dir = tmp_path / "test_session_no_summary"
        session_dir.mkdir(parents=True, exist_ok=True)

        transcript = [{"author": "Arquiteto", "content": "Arg", "turn": 1}]

        await SessionFiles.save_debate(
            session_dir,
            debate_num=2,
            topic="Topico sem resumo",
            transcript=transcript
        )

        debate_dir = session_dir / "debate_002"
        assert (debate_dir / "metadata.json").exists()
        assert (debate_dir / "transcript.json").exists()
        assert not (debate_dir / "summary.json").exists()

    async def test_save_session_summary(self, tmp_path):
        """Testa salvamento de resumo da sessao."""
        from server import SessionFiles

        session_dir = tmp_path / "test_session_summary"
        session_dir.mkdir(parents=True, exist_ok=True)

        summary_data = {
            "session_id": "test-session",
            "total_debates": 5,
            "duration_hours": 8.0,
            "topics": ["Topico 1", "Topico 2"],
            "summary": "Resumo executivo da sessao"
        }

        await SessionFiles.save_session_summary(session_dir, summary_data)

        summary_file = session_dir / "nightly_summary.json"
        assert summary_file.exists()

        with open(summary_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
            assert saved["session_id"] == "test-session"
            assert saved["total_debates"] == 5
            assert len(saved["topics"]) == 2

    async def test_save_debate_with_unicode(self, tmp_path):
        """Testa salvamento com caracteres especiais."""
        from server import SessionFiles

        session_dir = tmp_path / "test_unicode"
        session_dir.mkdir(parents=True, exist_ok=True)

        transcript = [
            {"author": "Arquiteto", "content": "Argumento com acentos: ç, ã, ü", "turn": 1},
        ]

        await SessionFiles.save_debate(
            session_dir,
            debate_num=1,
            topic="Tópico com acentos",
            transcript=transcript
        )

        debate_dir = session_dir / "debate_001"
        with open(debate_dir / "transcript.json", "r", encoding="utf-8") as f:
            saved = json.load(f)
            assert saved[0]["content"] == "Argumento com acentos: ç, ã, ü"


# Import necessario para patch
from unittest.mock import patch
