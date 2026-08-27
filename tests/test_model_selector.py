"""
Testes unitários para o Seletor Adaptativo de Modelos e Circuit Breaker
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from stability.model_selector import AdaptiveModelSelector, ModelHealthRecord


class TestModelHealthRecord:
    """Testa o registro de saúde de modelos individuais."""

    def test_record_success_resets_failures(self):
        rec = ModelHealthRecord(name="qwen3.5:9b", size_bytes=6600000000)
        rec.failure_count = 2
        rec.record_success(latency_sec=12.5)

        assert rec.success_count == 1
        assert rec.avg_latency_sec == 12.5
        assert rec.is_healthy is True
        assert rec.failure_count == 1

    def test_record_failure_triggers_cooldown(self):
        rec = ModelHealthRecord(name="qwen3.5:9b", size_bytes=6600000000)
        rec.record_failure("Timeout de 120s", cooldown_seconds=60.0)

        assert rec.failure_count == 1
        assert rec.is_healthy is False
        assert rec.is_available() is False


class TestAdaptiveModelSelector:
    """Testa a escada de modelos e o fallback resiliente."""

    @pytest.mark.asyncio
    async def test_fetch_local_models_sorting(self):
        selector = AdaptiveModelSelector()

        mock_tags = {
            "models": [
                {"name": "nomic-embed-text:latest", "size": 274000000},
                {"name": "qwen2.5:7b", "size": 4700000000},
                {"name": "qwen3.5:9b", "size": 6600000000}
            ]
        }

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.json.return_value = mock_tags
            mock_resp.raise_for_status = MagicMock()
            mock_get.return_value = mock_resp

            models = await selector.fetch_local_models(force_refresh=True)

            # nomic-embed-text deve ser ignorado
            assert len(models) == 2
            # Maior modelo primeiro (qwen3.5:9b)
            assert models[0]["name"] == "qwen3.5:9b"
            assert models[1]["name"] == "qwen2.5:7b"

    @pytest.mark.asyncio
    async def test_ladder_starts_with_preferred(self):
        selector = AdaptiveModelSelector()
        selector.cached_models = [
            {"name": "qwen3.5:9b", "size": 6600000000},
            {"name": "qwen2.5:7b", "size": 4700000000}
        ]

        ladder = await selector.get_model_ladder(preferred_model="qwen2.5:7b")
        assert ladder[0] == "qwen2.5:7b"
        assert ladder[1] == "qwen3.5:9b"

    @pytest.mark.asyncio
    async def test_infer_with_fallback_on_timeout(self):
        selector = AdaptiveModelSelector()
        selector.cached_models = [
            {"name": "qwen3.5:9b", "size": 6600000000},
            {"name": "qwen2.5:7b", "size": 4700000000}
        ]

        fallback_events = []

        async def callback(evt):
            fallback_events.append(evt)

        mock_success_resp = MagicMock()
        mock_success_resp.json.return_value = {
            "message": {"content": "Resposta estável do modelo 7B"}
        }
        mock_success_resp.raise_for_status = MagicMock()

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                import httpx
                raise httpx.ReadTimeout("Timeout na inferência")
            return mock_success_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            content, effective_model, latency = await selector.infer_with_adaptive_fallback(
                messages=[{"role": "user", "content": "Olá"}],
                preferred_model="qwen3.5:9b",
                step_timeout_sec=10.0,
                progress_callback=callback
            )

            assert effective_model == "qwen2.5:7b"
            assert content == "Resposta estável do modelo 7B"
            assert len(fallback_events) == 1
            assert fallback_events[0]["from_model"] == "qwen3.5:9b"
            assert fallback_events[0]["to_model"] == "qwen2.5:7b"
