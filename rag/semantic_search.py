"""
THZ Minds — Busca Semantica
Busca argumentos relevantes e constroi contexto para o debate.
"""

import logging
from typing import List, Dict, Optional

from .embedder import Embedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class SemanticSearch:
    """Busca semantica de argumentos no historico de debates."""

    def __init__(self, embedder: Embedder = None, store: VectorStore = None):
        self.embedder = embedder or Embedder()
        self.store = store or VectorStore()
        self._warned_unavailable = False

    async def buscar_argumentos_similares(
        self,
        query: str,
        agent_filter: str = None,
        topic_filter: str = None,
        top_k: int = 5
    ) -> List[Dict]:
        """Busca argumentos semanticamente similares a query."""
        # Verificar disponibilidade uma vez
        if self.embedder.available is None:
            await self.embedder.check_availability()

        if self.embedder.available is False:
            if not self._warned_unavailable:
                logger.info("[RAG] Embeddings indisponiveis — busca semantica desabilitada")
                self._warned_unavailable = True
            return []

        embedding = await self.embedder.embed(query)
        if not embedding:
            return []

        blob = self.embedder.to_blob(embedding)
        return await self.store.search_similar(
            blob, top_k=top_k,
            agent_filter=agent_filter,
            topic_filter=topic_filter
        )

    async def construir_knowledge_context(
        self,
        topic: str,
        current_agent: str,
        history: List[Dict],
        max_args: int = 3
    ) -> str:
        """Constrói knowledge_context para injection no prompt do agente.

        Busca argumentos de OUTROS agentes sobre topicos similares.
        Exclui argumentos do proprio agente para evitar auto-referencia.
        """
        # Buscar argumentos similares ao topico
        resultados = await self.buscar_argumentos_similares(
            query=topic,
            agent_filter=current_agent,  # Exclui proprio agente
            top_k=max_args * 2  # Buscar mais para ter opcoes
        )

        if not resultados:
            return ""

        # Filtrar apenas argumentos com score > 0.3
        relevantes = [r for r in resultados if r.get("score", 0) > 0.3]

        if not relevantes:
            return ""

        # Montar contexto
        context = "\n\n## Argumentos relevantes de debates anteriores:\n"
        for i, arg in enumerate(relevantes[:max_args]):
            # Buscar conteudo completo do argumento
            msg = await self.store.get_message_by_id(arg["message_id"])
            if msg:
                content = msg["content"][:300]  # Limitar tamanho
                context += f"- [{arg['agent_name']}] (similaridade: {arg['score']:.2f}): {content}...\n"

        context += "\nUse esses argumentos como referencia, mas traga novas perspectivas.\n"
        return context

    async def indexar_argumentos_pendentes(self, batch_size: int = 32) -> int:
        """Indexa argumentos que ainda nao foram embutidos."""
        # Buscar IDs nao indexados
        unindexed = await self.store.get_unindexed_message_ids()
        if not unindexed:
            return 0

        logger.info(f"[RAG] Indexando {len(unindexed)} argumentos pendentes...")
        stored = 0

        for i in range(0, len(unindexed), batch_size):
            batch_ids = unindexed[i:i + batch_size]
            records = []

            for msg_id in batch_ids:
                msg = await self.store.get_message_by_id(msg_id)
                if not msg:
                    continue

                # Gerar embedding do conteudo
                embedding = await self.embedder.embed(msg["content"])
                if not embedding:
                    continue

                blob = self.embedder.to_blob(embedding)

                # Buscar topico da conversa
                topic = await self._get_topic_for_message(msg["conversation_id"])

                records.append((msg_id, msg["agent_name"], topic or "", blob))

            # Armazenar batch
            if records:
                stored += await self.store.store_batch(records)

            logger.info(f"[RAG] Batch {i // batch_size + 1}: {len(records)} embeddings")

        logger.info(f"[RAG] Total indexado: {stored}")
        return stored

    async def _get_topic_for_message(self, conversation_id: str) -> Optional[str]:
        """Busca topico de uma conversa."""
        import aiosqlite
        try:
            async with aiosqlite.connect(self.store.db_path) as db:
                cursor = await db.execute(
                    "SELECT topic FROM conversations WHERE id = ?",
                    (conversation_id,)
                )
                row = await cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None
