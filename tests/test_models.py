"""
Testes para os modelos Pydantic do THz Room
"""

import pytest
from pydantic import ValidationError


class TestAgentDecision:
    """Testes para o modelo AgentDecision."""

    def test_valid_continue(self):
        """Testa criacao de decisao CONTINUE valida."""
        from server import AgentDecision
        decision = AgentDecision(
            argument="Kafka e mais escalavel para alta volumetria.",
            status="CONTINUE"
        )
        assert decision.argument == "Kafka e mais escalavel para alta volumetria."
        assert decision.status == "CONTINUE"

    def test_valid_consensus(self):
        """Testa criacao de decisao CONSENSUS valida."""
        from server import AgentDecision
        decision = AgentDecision(
            argument="Concordo com a solucao proposta.",
            status="CONSENSUS"
        )
        assert decision.status == "CONSENSUS"

    def test_valid_force_stop(self):
        """Testa criacao de decisao FORCE_STOP valida."""
        from server import AgentDecision
        decision = AgentDecision(
            argument="Sistema detectou problema.",
            status="FORCE_STOP"
        )
        assert decision.status == "FORCE_STOP"

    def test_invalid_status(self):
        """Testa que status invalido gera erro."""
        from server import AgentDecision
        with pytest.raises(ValidationError):
            AgentDecision(
                argument="Teste",
                status="INVALIDO"
            )

    def test_missing_argument(self):
        """Testa que argumento faltante gera erro."""
        from server import AgentDecision
        with pytest.raises(ValidationError):
            AgentDecision(status="CONTINUE")

    def test_empty_argument(self):
        """Testa que argumento vazio e permitido (string vazia)."""
        from server import AgentDecision
        decision = AgentDecision(argument="", status="CONTINUE")
        assert decision.argument == ""


class TestSingleDebateRequest:
    """Testes para o modelo SingleDebateRequest."""

    def test_valid_request(self):
        """Testa criacao de requisicao valida."""
        from server import SingleDebateRequest
        req = SingleDebateRequest(
            mode="single",
            topic="Teste de topic"
        )
        assert req.mode == "single"
        assert req.topic == "Teste de topic"
        assert req.max_turns == 48  # default
        assert req.num_ctx == 8192  # default
        assert req.model is None  # default

    def test_custom_params(self):
        """Testa parametros customizados."""
        from server import SingleDebateRequest
        req = SingleDebateRequest(
            mode="single",
            topic="Teste",
            max_turns=12,
            num_ctx=4096,
            model="qwen2.5:7b"
        )
        assert req.max_turns == 12
        assert req.num_ctx == 4096
        assert req.model == "qwen2.5:7b"

    def test_invalid_mode(self):
        """Testa que modo invalido gera erro."""
        from server import SingleDebateRequest
        with pytest.raises(ValidationError):
            SingleDebateRequest(mode="invalido", topic="Teste")

    def test_max_turns_too_low(self):
        """Testa que max_turns abaixo do minimo gera erro."""
        from server import SingleDebateRequest
        with pytest.raises(ValidationError):
            SingleDebateRequest(mode="single", topic="Teste", max_turns=2)

    def test_max_turns_too_high(self):
        """Testa que max_turns acima do maximo gera erro."""
        from server import SingleDebateRequest
        with pytest.raises(ValidationError):
            SingleDebateRequest(mode="single", topic="Teste", max_turns=100)

    def test_num_ctx_too_low(self):
        """Testa que num_ctx abaixo do minimo gera erro."""
        from server import SingleDebateRequest
        with pytest.raises(ValidationError):
            SingleDebateRequest(mode="single", topic="Teste", num_ctx=1024)


class TestAutonomousSessionRequest:
    """Testes para o modelo AutonomousSessionRequest."""

    def test_valid_request(self):
        """Testa criacao de requisicao valida."""
        from server import AutonomousSessionRequest
        req = AutonomousSessionRequest(mode="autonomous")
        assert req.mode == "autonomous"
        assert req.duration_hours == 8.0  # default
        assert req.num_ctx == 8192  # default
        assert req.model is None  # default

    def test_custom_duration(self):
        """Testa duracao customizada."""
        from server import AutonomousSessionRequest
        req = AutonomousSessionRequest(mode="autonomous", duration_hours=4.5)
        assert req.duration_hours == 4.5

    def test_invalid_mode(self):
        """Testa que modo invalido gera erro."""
        from server import AutonomousSessionRequest
        with pytest.raises(ValidationError):
            AutonomousSessionRequest(mode="single")  # Wrong mode

    def test_duration_too_short(self):
        """Testa que duracao muito curta gera erro."""
        from server import AutonomousSessionRequest
        with pytest.raises(ValidationError):
            AutonomousSessionRequest(mode="autonomous", duration_hours=0.1)

    def test_duration_too_long(self):
        """Testa que duracao muito longa gera erro."""
        from server import AutonomousSessionRequest
        with pytest.raises(ValidationError):
            AutonomousSessionRequest(mode="autonomous", duration_hours=30)
