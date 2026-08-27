"""
THZ Minds — Script de Indexacao de Embeddings
Indexa argumentos pendentes no banco de embeddings.
"""

import asyncio
import logging
import sys
import os

# Adicionar diretorio pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.embedder import Embedder
from rag.vector_store import VectorStore
from rag.semantic_search import SemanticSearch
from rag.migrate_db import migrate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)


async def main():
    """Indexa argumentos pendentes."""
    logger.info("[INDEX] Iniciando migracao do schema...")
    await migrate()

    logger.info("[INDEX] Verificando modelo de embeddings...")
    embedder = Embedder()

    # Testar embedding
    test = await embedder.embed("teste de conexao")
    if not test:
        logger.error("[INDEX] Modelo de embeddings nao disponivel!")
        logger.info("[INDEX] Execute: ollama pull nomic-embed-text")
        return

    logger.info(f"[INDEX] Modelo OK (dim={len(test)})")

    # Indexar
    search = SemanticSearch(embedder=embedder)
    count = await search.indexar_argumentos_pendentes()

    logger.info(f"[INDEX] Concluido! {count} argumentos indexados.")

    # Estatisticas
    store = VectorStore()
    total = await store.count()
    logger.info(f"[INDEX] Total de embeddings no banco: {total}")


if __name__ == "__main__":
    asyncio.run(main())
