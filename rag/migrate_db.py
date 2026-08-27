"""
THZ Minds — Migracao do Schema SQLite
Adiciona tabelas para embeddings RAG e health monitoring.
"""

import aiosqlite
import logging

logger = logging.getLogger(__name__)

DB_PATH = "data/thz-room-cortex.db"

NEW_TABLES = """
-- Tabela de embeddings para busca semantica (RAG)
CREATE TABLE IF NOT EXISTS argument_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE,
    agent_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

-- Indices para embeddings
CREATE INDEX IF NOT EXISTS idx_emb_agent ON argument_embeddings(agent_name);
CREATE INDEX IF NOT EXISTS idx_emb_topic ON argument_embeddings(topic);
CREATE INDEX IF NOT EXISTS idx_emb_message ON argument_embeddings(message_id);

-- Tabela de health monitoring do debate
CREATE TABLE IF NOT EXISTS debate_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn INTEGER NOT NULL,
    diversity_score REAL,
    trend TEXT,
    repetition_count INTEGER DEFAULT 0,
    plagiarism_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

-- Indice para health
CREATE INDEX IF NOT EXISTS idx_health_conv ON debate_health(conversation_id);
"""


async def migrate():
    """Executa a migracao do schema."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")

        logger.info("[MIGRATE] Adicionando novas tabelas...")
        await db.executescript(NEW_TABLES)
        await db.commit()

        # Verificar tabelas
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in await cursor.fetchall()]
        logger.info(f"[MIGRATE] Tabelas: {tables}")

        # Verificar sqlite-vec
        try:
            await db.execute("SELECT vec_version()")
            logger.info("[MIGRATE] sqlite-vec disponivel")
        except Exception:
            logger.warning("[MIGRATE] sqlite-vec NAO disponivel — embeddings serao armazenados como BLOB puro")


async def verify():
    """Verifica se as tabelas existem."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('argument_embeddings', 'debate_health')")
        tables = [row[0] for row in await cursor.fetchall()]
        return {
            "argument_embeddings": "argument_embeddings" in tables,
            "debate_health": "debate_health" in tables,
        }


if __name__ == "__main__":
    import asyncio
    asyncio.run(migrate())
