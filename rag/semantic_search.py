"""
THZ Minds — Busca Semantica, Agrupamento (Clustering) e Grafo de Conhecimento
Busca argumentos relevantes, relaciona topicos e constroi contexto para o debate.
"""

import aiosqlite
import logging
from typing import List, Dict, Optional, Tuple

from .embedder import Embedder
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class SemanticSearch:
    """Busca semantica de argumentos e grafo de conhecimento no historico de debates."""

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
        Busca argumentos de outros agentes sobre topicos similares e conexoes do grafo."""
        context = ""

        # 1. Argumentos similares
        resultados = await self.buscar_argumentos_similares(
            query=topic,
            agent_filter=current_agent,
            top_k=max_args * 2
        )

        relevantes = [r for r in resultados if r.get("score", 0) > 0.3] if resultados else []
        if relevantes:
            context += "\n\n## Argumentos relevantes de debates anteriores:\n"
            for r in relevantes[:max_args]:
                msg = await self.store.get_message_by_id(r["message_id"])
                if msg:
                    content = msg["content"][:280]
                    context += f"- [{r['agent_name']}] (similaridade: {r['score']:.2f}): {content}...\n"
            context += "\nUse esses argumentos como referencia, mas traga novas perspectivas.\n"

        # 2. Conexoes do Knowledge Graph
        try:
            related = await self.get_related_topics(topic, limit=3)
            if related:
                context += "\n## Topicos Conectados no Grafo de Conhecimento:\n"
                for rel in related:
                    context += f"- Conexao com '{rel['target_topic']}' ({rel['relationship']}, forca: {rel['strength']:.2f})\n"
        except Exception:
            pass

        return context

    async def link_topics(
        self,
        source_topic: str,
        target_topic: str,
        relationship: str = "similar",
        strength: float = 0.8
    ) -> bool:
        """Cria ou atualiza uma relacao no knowledge_graph."""
        try:
            async with aiosqlite.connect(self.store.db_path) as db:
                await db.execute("""
                    INSERT INTO knowledge_graph (source_topic, target_topic, relationship, strength)
                    VALUES (?, ?, ?, ?)
                """, (source_topic, target_topic, relationship, strength))
                await db.commit()
                return True
        except Exception as e:
            logger.debug(f"[GRAPH] Erro ao linkar topicos: {e}")
            return False

    async def get_related_topics(self, topic: str, limit: int = 5) -> List[Dict]:
        """Recupera topicos conectados no knowledge_graph."""
        try:
            async with aiosqlite.connect(self.store.db_path) as db:
                rows = await db.execute_fetchall("""
                    SELECT target_topic, relationship, strength
                    FROM knowledge_graph
                    WHERE source_topic = ? OR target_topic = ?
                    ORDER BY strength DESC
                    LIMIT ?;
                """, (topic, topic, limit))
                return [
                    {
                        "target_topic": r[0] if r[0] != topic else topic,
                        "relationship": r[1],
                        "strength": r[2]
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.debug(f"[GRAPH] Erro ao buscar conexoes: {e}")
            return []

    async def cluster_topics(self, min_similarity: float = 0.65) -> Dict[str, List[str]]:
        """Agrupa topicos semelhantes com base na proximidade de embeddings."""
        try:
            async with aiosqlite.connect(self.store.db_path) as db:
                rows = await db.execute_fetchall("SELECT DISTINCT topic FROM topic_memory LIMIT 100")
                topics = [r[0] for r in rows if r[0]]

            if len(topics) < 2:
                return {"Geral": topics}

            clusters: Dict[str, List[str]] = {}
            embeddings: Dict[str, List[float]] = {}

            for t in topics:
                emb = await self.embedder.embed(t)
                if emb:
                    embeddings[t] = emb

            used = set()
            for i, (t1, e1) in enumerate(embeddings.items()):
                if t1 in used:
                    continue
                cluster_name = t1[:30] + "..." if len(t1) > 30 else t1
                clusters[cluster_name] = [t1]
                used.add(t1)

                for t2, e2 in embeddings.items():
                    if t2 in used or t1 == t2:
                        continue
                    sim = Embedder.cosine_similarity(e1, e2)
                    if sim >= min_similarity:
                        clusters[cluster_name].append(t2)
                        used.add(t2)
                        # Salva conexao no grafo
                        await self.link_topics(t1, t2, relationship="similar", strength=sim)

            return {k: v for k, v in clusters.items() if v}
        except Exception as e:
            logger.error(f"[CLUSTERING] Erro no agrupamento de topicos: {e}")
            return {}

    async def indexar_argumentos_pendentes(self, batch_size: int = 32) -> int:
        """Indexa argumentos que ainda nao foram embutidos."""
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

                embedding = await self.embedder.embed(msg["content"])
                if not embedding:
                    continue

                blob = self.embedder.to_blob(embedding)
                topic = await self._get_topic_for_message(msg["conversation_id"])

                records.append((msg_id, msg["agent_name"], topic or "", blob))

            if records:
                stored += await self.store.store_batch(records)

            logger.info(f"[RAG] Batch {i // batch_size + 1}: {len(records)} embeddings")

        logger.info(f"[RAG] Total indexado: {stored}")
        return stored

    async def _get_topic_for_message(self, conversation_id: str) -> Optional[str]:
        """Busca topico de uma conversa."""
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
