"""
Testes para o client.py do THz Room
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio


def make_mock_ws(events):
    """Cria um mock de WebSocket que retorna eventos e depois para."""
    mock_ws = AsyncMock()
    mock_ws.__aenter__ = AsyncMock(return_value=mock_ws)
    mock_ws.__aexit__ = AsyncMock(return_value=False)

    recv_side_effects = []
    for evt in events:
        recv_side_effects.append(json.dumps(evt))
    recv_side_effects.append(Exception("Fim dos eventos"))

    mock_ws.recv = AsyncMock(side_effect=recv_side_effects)
    mock_ws.send = AsyncMock()
    return mock_ws


class TestClient:

    async def test_run_single_payload(self):
        from client import run_single

        mock_ws = make_mock_ws([])

        with patch('client.websockets.connect', return_value=mock_ws):
            try:
                await run_single("Teste Kafka", 18, 8192, "qwen2.5:7b")
            except Exception:
                pass

            payload = json.loads(mock_ws.send.call_args[0][0])
            assert payload["mode"] == "single"
            assert payload["topic"] == "Teste Kafka"
            assert payload["max_turns"] == 18
            assert payload["num_ctx"] == 8192
            assert payload["model"] == "qwen2.5:7b"

    async def test_run_autonomous_payload(self):
        from client import run_autonomous

        mock_ws = make_mock_ws([])

        with patch('client.websockets.connect', return_value=mock_ws):
            try:
                await run_autonomous(4.0, 8192, None)
            except Exception:
                pass

            payload = json.loads(mock_ws.send.call_args[0][0])
            assert payload["mode"] == "autonomous"
            assert payload["duration_hours"] == 4.0
            assert payload["num_ctx"] == 8192
            assert payload["model"] is None

    async def test_run_session_turn_end(self):
        from client import _run_session

        events = [
            {
                "event": "turn_end",
                "data": {
                    "turn": 1, "agent": "Arquiteto",
                    "role": "Software Architect",
                    "argument": "Argumento de teste",
                    "status": "CONTINUE"
                }
            },
            {"event": "error", "data": {"message": "stop"}},
        ]
        mock_ws = make_mock_ws(events)

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "single", "topic": "Teste"})

        assert mock_ws.recv.call_count == 2

    async def test_run_session_debate_complete(self):
        from client import _run_session

        events = [
            {"event": "debate_complete", "data": {"reason": "consensus", "total_turns": 14}},
            {"event": "error", "data": {"message": "stop"}},  # sentinel to end loop
        ]
        mock_ws = make_mock_ws(events)

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "single", "topic": "Teste"})

        assert mock_ws.recv.call_count == 2

    async def test_run_session_error(self):
        from client import _run_session

        evt = {"event": "error", "data": {"message": "Fora do escopo"}}
        mock_ws = make_mock_ws([evt])

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "single", "topic": "Teste"})

        assert mock_ws.recv.call_count == 1

    async def test_run_session_session_complete(self):
        from client import _run_session

        evt = {
            "event": "session_complete",
            "data": {
                "total_debates": 5,
                "duration_hours": 8.0,
                "topics": ["A", "B"],
                "summary": "Resumo"
            }
        }
        mock_ws = make_mock_ws([evt])

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "autonomous", "duration_hours": 8})

        assert mock_ws.recv.call_count == 1

    async def test_run_session_connection_refused(self):
        from client import _run_session

        mock_ws = MagicMock()
        mock_ws.__aenter__ = AsyncMock(side_effect=ConnectionRefusedError)
        mock_ws.__aexit__ = AsyncMock(return_value=False)

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "single", "topic": "Teste"})

    async def test_run_session_multiple_events(self):
        from client import _run_session

        events = [
            {"event": "turn_start", "data": {"turn": 1, "agent": "Arquiteto", "role": "Architect"}},
            {"event": "turn_end", "data": {"turn": 1, "agent": "Arquiteto", "role": "Architect",
                                           "argument": "Arg", "status": "CONTINUE"}},
            {"event": "debate_complete", "data": {"reason": "consensus", "total_turns": 1}},
            {"event": "error", "data": {"message": "stop"}},
        ]
        mock_ws = make_mock_ws(events)

        with patch('client.websockets.connect', return_value=mock_ws):
            await _run_session({"mode": "single", "topic": "Teste"})

        assert mock_ws.recv.call_count == 4
