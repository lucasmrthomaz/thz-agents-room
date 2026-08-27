"""
THZ Minds — Gerenciamento de Embeddings
Gera embeddings vetoriais para argumentos do debate.
Gracefully degrades quando modelo nao esta disponivel.
"""

import struct
import logging
import httpx
from typing import List, Optional

logger = logging.getLogger(__name__)

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
DEFAULT_MODEL = "nomic-embed-text"
EMBEDDING_DIM = 768


class Embedder:
    """Gerencia embeddings via Ollama."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.dim = EMBEDDING_DIM
        self.available = None  # None = nao checado, True/False = checado

    async def check_availability(self) -> bool:
        """Verifica se o modelo de embeddings esta disponivel."""
        if self.available is not None:
            return self.available

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": self.model, "input": "teste"},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    self.available = True
                    logger.info(f"[EMBED] Modelo {self.model} disponivel")
                else:
                    self.available = False
                    logger.warning(f"[EMBED] Modelo {self.model} nao disponivel (HTTP {resp.status_code})")
        except Exception as e:
            self.available = False
            logger.warning(f"[EMBED] Modelo {self.model} nao disponivel: {e}")

        return self.available

    async def embed(self, text: str) -> Optional[List[float]]:
        """Gera embedding de um texto. Retorna None se indisponivel."""
        if self.available is False:
            return None

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    OLLAMA_EMBED_URL,
                    json={"model": self.model, "input": text},
                    timeout=30.0
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    self.available = True
                    return embeddings[0]
                return None
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    self.available = False
                    logger.debug(f"[EMBED] Modelo {self.model} nao encontrado (404)")
                else:
                    logger.error(f"[EMBED] Erro HTTP: {e}")
                return None
            except Exception as e:
                logger.error(f"[EMBED] Erro ao gerar embedding: {e}")
                return None

    async def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[Optional[List[float]]]:
        """Gera embeddings de varios textos em batch."""
        if self.available is False:
            return [None] * len(texts)

        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_results = []
            for text in batch:
                emb = await self.embed(text)
                batch_results.append(emb)
            results.extend(batch_results)
        return results

    @staticmethod
    def to_blob(embedding: List[float]) -> bytes:
        """Converte embedding para BLOB (float32 little-endian)."""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def from_blob(blob: bytes) -> List[float]:
        """Converte BLOB para embedding."""
        n = len(blob) // 4
        return list(struct.unpack(f"{n}f", blob))

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calcula similaridade cosseno entre dois vetores."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
