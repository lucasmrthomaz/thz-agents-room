"""
THZ Minds — Vector Store (sqlite-vec wrapper)
Armazenamento e busca de embeddings no SQLite.
"""

import aiosqlite
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DB_PATH = "data/thz-room-cortex.db"


class VectorStore:
    """Wrapper para armazenamento de embeddings no SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    async def store_embedding(self, message_id: int, agent_name: str, topic: str, embedding_blob: bytes) -> bool:
        """Armazena embedding de um argumento."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("""
                    INSERT OR REPLACE INTO argument_embeddings (message_id, agent_name, topic, embedding)
                    VALUES (?, ?, ?, ?)
                """, (message_id, agent_name, topic, embedding_blob))
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"[VECTOR] Erro ao armazenar embedding: {e}")
            return False

    async def store_batch(self, records: List[Tuple[int, str, str, bytes]]) -> int:
        """Armazena embeddings em batch. Retorna quantidade armazenada."""
        stored = 0
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.executemany("""
                    INSERT OR REPLACE INTO argument_embeddings (message_id, agent_name, topic, embedding)
                    VALUES (?, ?, ?, ?)
                """, records)
                await db.commit()
                stored = len(records)
        except Exception as e:
            logger.error(f"[VECTOR] Erro no batch store: {e}")
        return stored

    async def search_similar(self, embedding_blob: bytes, top_k: int = 5,
                             agent_filter: str = None, topic_filter: str = None) -> List[Dict]:
        """Busca argumentos mais similares por cosine similarity.
        Nota: Sem sqlite-vec, faz busca linear em memoria."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("PRAGMA journal_mode=WAL;")

                query = "SELECT id, message_id, agent_name, topic, embedding FROM argument_embeddings"
                params = []
                conditions = []

                if agent_filter:
                    conditions.append("agent_name != ?")
                    params.append(agent_filter)
                if topic_filter:
                    conditions.append("topic = ?")
                    params.append(topic_filter)

                if conditions:
                    query += " WHERE " + " AND ".join(conditions)

                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()

                if not rows:
                    return []

                # Calcular similaridade (busca linear)
                from .embedder import Embedder
                query_vec = Embedder.from_blob(embedding_blob)
                scored = []
                for row in rows:
                    id_, msg_id, agent, topic, emb_blob = row
                    db_vec = Embedder.from_blob(emb_blob)
                    sim = Embedder.cosine_similarity(query_vec, db_vec)
                    scored.append({
                        "id": id_,
                        "message_id": msg_id,
                        "agent_name": agent,
                        "topic": topic,
                        "score": sim,
                    })

                # Ordenar por score e retornar top-k
                scored.sort(key=lambda x: x["score"], reverse=True)
                return scored[:top_k]

        except Exception as e:
            logger.error(f"[VECTOR] Erro na busca: {e}")
            return []

    async def get_unindexed_message_ids(self) -> List[int]:
        """Retorna IDs de messages que ainda nao tem embedding."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    SELECT m.id FROM messages m
                    LEFT JOIN argument_embeddings ae ON m.id = ae.message_id
                    WHERE ae.id IS NULL
                    ORDER BY m.id
                """)
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"[VECTOR] Erro ao buscar nao indexados: {e}")
            return []

    async def get_message_by_id(self, message_id: int) -> Optional[Dict]:
        """Retorna uma message pelo ID."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, conversation_id, agent_name, content, status, turn FROM messages WHERE id = ?",
                    (message_id,)
                )
                row = await cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "conversation_id": row[1],
                        "agent_name": row[2],
                        "content": row[3],
                        "status": row[4],
                        "turn": row[5],
                    }
                return None
        except Exception as e:
            logger.error(f"[VECTOR] Erro ao buscar message: {e}")
            return None

    async def count(self) -> int:
        """Retorna quantidade de embeddings armazenados."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT COUNT(*) FROM argument_embeddings")
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
