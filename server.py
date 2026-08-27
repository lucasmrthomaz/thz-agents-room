"""
Multi-Agent Conversation Engine - Autonomous Mode
Arquitetura: FastAPI + WebSockets + SQLite (thz-room-cortex.db) + Ollama

8 Agentes: 5 Tecnicos + 3 de Negocio
Modos: Single (sob demanda) + Autonomous (sessao noturna)
"""

import asyncio
import json
import logging
import os
import signal
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import aiosqlite
import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Modulos de estabilidade e RAG
from stability.context_manager import ContextManager
from stability.loop_detector import LoopDetector
from stability.quality_monitor import QualityMonitor
from rag.semantic_search import SemanticSearch
from tools import get_tool_registry
from export import ReportGenerator
from guardrails import ScopeGuard, get_scope_guard, get_sandbox
from teamwork import (
    EngineeringPipeline,
    ContentPipeline,
    TeamworkSessionRequest,
    TeamworkSessionResult,
    WorkspaceManager,
    TeamworkMode,
)
from scenarios import get_scenario_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ThzRoom")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = BASE_DIR / "sessions"
DB_PATH = DATA_DIR / "thz-room-cortex.db"

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
DEFAULT_MODEL = "qwen2.5:7b"

# =====================================================================
# SHUTDOWN GRACEFUL
# =====================================================================

class GracefulShutdown:
    """Gerencia shutdown gracioso com salvamento de dados."""
    def __init__(self):
        self.should_exit = False
        self.current_session = None
        self.current_debate = None
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("[SHUTDOWN] Sinal recebido. Salvando dados...")
        self.should_exit = True

    async def save_current_state(self):
        """Salva o estado atual da sessao em caso de interrupcao."""
        if self.current_session:
            try:
                session_dir = SessionFiles.get_session_dir(self.current_session["id"])
                summary_data = {
                    "session_id": self.current_session["id"],
                    "total_debates": self.current_session.get("debate_count", 0),
                    "duration_hours": self.current_session.get("duration", 0),
                    "topics": self.current_session.get("topics", []),
                    "interrupted": True,
                    "interrupted_at": datetime.now().isoformat(),
                    "created_at": self.current_session.get("start_time", datetime.now().isoformat())
                }
                await SessionFiles.save_session_summary(session_dir, summary_data)
                logger.info(f"[SHUTDOWN] Sessao salva em {session_dir}")
            except Exception as e:
                logger.error(f"[SHUTDOWN] Erro ao salvar sessao: {e}")

shutdown_manager = GracefulShutdown()

# =====================================================================
# 1. ESQUEMAS DE DADOS
# =====================================================================

from enum import Enum

class ActionType(Enum):
    """Categorias de ação com níveis de segurança diferentes."""
    READ_ONLY = "read_only"      # Gerar texto, ler DB — permitido
    WRITE_DB = "write_db"        # Salvar mensagem — permitido
    CONSENSUS = "consensus"      # Marcar consenso — requer validação
    DELEGATE = "delegate"         # Delegar tarefa — requer validação
    DANGEROUS = "dangerous"      # Deletar, modificar config — BLOQUEADO sem humano


async def requires_human_approval(action: ActionType, context: dict = None) -> bool:
    """Determina se uma ação requer aprovação humana."""
    if action == ActionType.DANGEROUS:
        return True  # Sempre requer humano
    if action == ActionType.CONSENSUS:
        # Tópicos muito discutidos precisam de aprovação
        times_discussed = (context or {}).get("times_discussed", 0)
        return times_discussed > 3
    if action == ActionType.DELEGATE:
        return True  # Sempre requer humano
    return False


async def calculate_vote_weight(agent_name: str, all_agent_skills: dict) -> float:
    """Calcula peso de voto de um agente baseado na sua expertise."""
    if agent_name in all_agent_skills:
        skills = all_agent_skills[agent_name]
        if skills:
            avg_expertise = sum(s.get("expertise_level", 0.5) for s in skills) / len(skills)
            # Peso entre 0.5 (iniciante) e 1.0 (expert)
            return min(1.0, 0.5 + (avg_expertise * 0.5))
    return 0.5  # Peso padrão


class AgentDecision(BaseModel):
    argument: str = Field(
        description="Argumento tecnico detalhado em Portugues do Brasil (pt-BR)."
    )
    status: Literal["CONTINUE", "CONSENSUS", "FORCE_STOP"] = Field(
        description="CONTINUE para manter a discusao; CONSENSUS quando concordar com a maioria dos pontos principais; FORCE_STOP quando o sistema forca parada."
    )
    question_to: Optional[str] = Field(
        default=None,
        description="Nome do agente alvo (ex: 'SRE'), se tiver duvida sobre argumento dele. Null se sem pergunta."
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Raciocinio interno antes de responder (nao enviado ao debate). Analise o que foi dito, dados concretos, se concorda com a maioria."
    )
    tool_call: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Chamada opcional de ferramenta para enriquecer a analise: {'tool': 'web_search'|'db_query'|'file_read'|'code_execute', 'params': {...}}"
    )

class SingleDebateRequest(BaseModel):
    mode: Literal["single"] = "single"
    topic: str
    max_turns: int = Field(default=48, ge=6, le=50)
    num_ctx: int = Field(default=8192, ge=4096, le=32768)
    model: Optional[str] = None

class AutonomousSessionRequest(BaseModel):
    mode: Literal["autonomous"] = "autonomous"
    duration_hours: float = Field(default=8.0, ge=0.5, le=24.0)
    max_turns: int = Field(default=48, ge=6, le=50)
    num_ctx: int = Field(default=8192, ge=4096, le=32768)
    model: Optional[str] = None

# =====================================================================
# 2. SELECAO DINAMICA DE MODELO
# =====================================================================

async def discover_best_model() -> str:
    """Consulta Ollama e retorna o melhor modelo saudável disponível (qwen3.5:9b > qwen2.5:7b > menores)."""
    try:
        from stability.model_selector import get_model_selector
        selector = get_model_selector()
        best_model = await selector.get_best_healthy_model()
        logger.info(f"[ADAPTIVE-MODEL] Melhor modelo selecionado automaticamente: {best_model}")
        return best_model
    except Exception as e:
        logger.warning(f"Falha ao descobrir modelos via selector: {e}. Usando default: {DEFAULT_MODEL}")
        return DEFAULT_MODEL

async def resolve_model(requested: Optional[str]) -> str:
    if requested and requested != "auto":
        logger.info(f"Modelo definido pelo usuario: {requested}")
        return requested
    env_model = os.environ.get("OLLAMA_MODEL")
    if env_model:
        logger.info(f"Modelo via variavel de ambiente: {env_model}")
        return env_model
    return await discover_best_model()


async def _migrate_db(db):
    """Migra banco de dados existente, adicionando colunas novas."""
    # Obter colunas existentes
    async with db.execute("PRAGMA table_info(conversations)") as cursor:
        conv_cols = {row[1] for row in await cursor.fetchall()}

    async with db.execute("PRAGMA table_info(messages)") as cursor:
        msg_cols = {row[1] for row in await cursor.fetchall()}

    # Adicionar colunas novas em conversations
    if "summary_short" not in conv_cols:
        await db.execute("ALTER TABLE conversations ADD COLUMN summary_short TEXT;")
        logger.info("[MIGRATE] Adicionado summary_short em conversations")

    if "summary_full" not in conv_cols:
        await db.execute("ALTER TABLE conversations ADD COLUMN summary_full TEXT;")
        logger.info("[MIGRATE] Adicionado summary_full em conversations")

    # Adicionar coluna nova em messages
    if "idempotency_key" not in msg_cols:
        await db.execute("ALTER TABLE messages ADD COLUMN idempotency_key TEXT;")
        logger.info("[MIGRATE] Adicionado idempotency_key em messages")

    await db.commit()

# =====================================================================
# 3. PERSISTENCIA - thz-room-cortex.db
# =====================================================================

class CortexDB:
    """Gerencia o banco de dados 'inteligencia interna' do sistema."""

    @staticmethod
    async def init():
        DATA_DIR.mkdir(exist_ok=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            await db.execute("PRAGMA foreign_keys = ON;")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    session_id TEXT,
                    summary_short TEXT,
                    summary_full TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    turn INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
            """)

            # Migracao: adicionar colunas novas em bancos existentes
            await _migrate_db(db)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS topic_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL UNIQUE,
                    category TEXT,
                    times_discussed INTEGER DEFAULT 1,
                    last_consensus BOOLEAN,
                    last_discussed_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS agent_skills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    skill_domain TEXT NOT NULL,
                    expertise_level REAL DEFAULT 0.5,
                    times_applied INTEGER DEFAULT 0,
                    consensus_contributions INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_name, skill_domain)
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS debate_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_type TEXT NOT NULL,
                    description TEXT,
                    example_data TEXT,
                    success_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS argument_embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL UNIQUE,
                    agent_name TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS argument_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT,
                    conversation_id TEXT,
                    agent_name TEXT,
                    quality_score REAL,
                    novelty_score REAL,
                    expertise_alignment REAL,
                    overall_score REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS debate_state (
                    conversation_id TEXT PRIMARY KEY,
                    topic TEXT,
                    current_turn INTEGER,
                    history_json TEXT,
                    status TEXT DEFAULT 'active',
                    session_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_topic TEXT NOT NULL,
                    target_topic TEXT NOT NULL,
                    relationship TEXT DEFAULT 'similar',
                    strength REAL DEFAULT 0.8,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS teamwork_sessions (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    status TEXT DEFAULT 'completed',
                    output_dir TEXT NOT NULL,
                    executive_summary TEXT,
                    total_steps INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS teamwork_artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT,
                    author_role TEXT,
                    content_length INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_agent ON argument_embeddings(agent_name);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_topic ON argument_embeddings(topic);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_message ON argument_embeddings(message_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_kg_source ON knowledge_graph(source_topic);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_kg_target ON knowledge_graph(target_topic);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_tw_session ON teamwork_artifacts(session_id);")
            await db.commit()
            logger.info(f"Cortex DB inicializado: {DB_PATH}")

    @staticmethod
    async def save_conversation(conversation_id: str, topic: str, session_id: str = None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR IGNORE INTO conversations (id, topic, session_id) VALUES (?, ?, ?);",
                (conversation_id, topic, session_id)
            )
            await db.commit()

    @staticmethod
    async def save_message(conversation_id: str, agent_name: str, content: str, status: str, turn: int):
        async with aiosqlite.connect(DB_PATH) as db:
            idempotency_key = f"{conversation_id}:{turn}:{agent_name}"
            await db.execute(
                "INSERT OR IGNORE INTO messages (conversation_id, agent_name, content, status, turn, idempotency_key) VALUES (?, ?, ?, ?, ?, ?);",
                (conversation_id, agent_name, content, status, turn, idempotency_key)
            )
            await db.commit()

    @staticmethod
    async def update_conversation_summary(conversation_id: str, summary_short: str, summary_full: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE conversations SET summary_short = ?, summary_full = ? WHERE id = ?;",
                (summary_short, summary_full, conversation_id)
            )
            await db.commit()

    @staticmethod
    async def save_teamwork_session(
        session_id: str, project_name: str, mode: str, goal: str,
        output_dir: str, executive_summary: str, total_steps: int,
        artifacts: list = None, status: str = "completed"
    ):
        """Salva a sessão de Teamwork e seus artefatos no Cortex DB."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR REPLACE INTO teamwork_sessions
                    (id, project_name, mode, goal, status, output_dir, executive_summary, total_steps)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (session_id, project_name, mode, goal, status, output_dir, executive_summary, total_steps))

            if artifacts:
                for art in artifacts:
                    path = art.get("path") if isinstance(art, dict) else getattr(art, "path", str(art))
                    f_type = art.get("file_type") if isinstance(art, dict) else getattr(art, "file_type", "")
                    role = art.get("author_role") if isinstance(art, dict) else getattr(art, "author_role", "")
                    content = art.get("content") if isinstance(art, dict) else getattr(art, "content", "")
                    c_len = len(content) if content else 0
                    await db.execute("""
                        INSERT INTO teamwork_artifacts
                            (session_id, project_name, file_path, file_type, author_role, content_length)
                        VALUES (?, ?, ?, ?, ?, ?);
                    """, (session_id, project_name, path, f_type, role, c_len))

            await db.commit()

    @staticmethod
    async def get_recent_teamwork_sessions(limit: int = 30) -> List[Dict]:
        """Retorna sessões recentes de Teamwork com seus artefatos associados."""
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("""
                SELECT id, project_name, mode, goal, status, output_dir, executive_summary, total_steps, created_at
                FROM teamwork_sessions
                ORDER BY created_at DESC LIMIT ?;
            """, (limit,))
            results = []
            for r in rows:
                s_id = r[0]
                art_rows = await db.execute_fetchall("""
                    SELECT file_path, file_type, author_role, content_length FROM teamwork_artifacts WHERE session_id = ?;
                """, (s_id,))
                files = [{"path": a[0], "file_type": a[1], "author_role": a[2], "size_bytes": a[3]} for a in art_rows]
                results.append({
                    "session_id": s_id,
                    "project_name": r[1],
                    "mode": r[2],
                    "goal": r[3],
                    "status": r[4],
                    "output_dir": r[5],
                    "executive_summary": r[6],
                    "total_steps": r[7],
                    "created_at": r[8],
                    "files": files,
                    "total_files": len(files)
                })
            return results

    @staticmethod
    async def update_topic_memory(topic: str, consensus: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO topic_memory (topic, last_consensus, last_discussed_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(topic) DO UPDATE SET
                    times_discussed = times_discussed + 1,
                    last_consensus = excluded.last_consensus,
                    last_discussed_at = CURRENT_TIMESTAMP;
            """, (topic, consensus))
            await db.commit()

    @staticmethod
    async def update_agent_skills(agent_name: str, domain: str, contributed_to_consensus: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO agent_skills (agent_name, skill_domain, times_applied, consensus_contributions, expertise_level)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(agent_name, skill_domain) DO UPDATE SET
                    times_applied = times_applied + 1,
                    consensus_contributions = consensus_contributions + excluded.consensus_contributions,
                    expertise_level = CAST(consensus_contributions + excluded.consensus_contributions AS REAL) / (times_applied + 1);
            """, (agent_name, domain, 1 if contributed_to_consensus else 0, 1.0 if contributed_to_consensus else 0.0))
            await db.commit()

    @staticmethod
    async def save_argument_score(
        message_id: str, conversation_id: str, agent_name: str,
        quality_score: float, novelty_score: float,
        expertise_alignment: float, overall_score: float
    ):
        """Persiste scores de qualidade de um argumento."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO argument_scores
                    (message_id, conversation_id, agent_name, quality_score, novelty_score, expertise_alignment, overall_score)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (message_id, conversation_id, agent_name, quality_score, novelty_score, expertise_alignment, overall_score))
            await db.commit()

    @staticmethod
    async def save_debate_state(
        conversation_id: str, topic: str, current_turn: int,
        history: list, status: str = "active", session_id: str = None
    ):
        """Salva estado do debate para retomada posterior."""
        import json
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO debate_state (conversation_id, topic, current_turn, history_json, status, session_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    current_turn = excluded.current_turn,
                    history_json = excluded.history_json,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP;
            """, (conversation_id, topic, current_turn, json.dumps(history, ensure_ascii=False), status, session_id))
            await db.commit()

    @staticmethod
    async def get_debate_state(conversation_id: str) -> Optional[Dict]:
        """Recupera estado de um debate pausado."""
        import json
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT topic, current_turn, history_json, status, session_id FROM debate_state WHERE conversation_id = ?",
                (conversation_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "topic": row[0],
                    "current_turn": row[1],
                    "history": json.loads(row[2]) if row[2] else [],
                    "status": row[3],
                    "session_id": row[4]
                }
            return None

    @staticmethod
    async def get_discussed_topics() -> List[str]:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("SELECT topic FROM topic_memory ORDER BY last_discussed_at DESC LIMIT 50;")
            return [r[0] for r in rows]

    @staticmethod
    async def get_agent_skills() -> Dict[str, List[Dict]]:
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall(
                "SELECT agent_name, skill_domain, expertise_level FROM agent_skills ORDER BY expertise_level DESC;"
            )
            skills: Dict[str, List[Dict]] = {}
            for name, domain, level in rows:
                if name not in skills:
                    skills[name] = []
                skills[name].append({"domain": domain, "level": level})
            return skills

    @staticmethod
    async def get_recent_debates(limit: int = 20) -> List[Dict]:
        """Retorna os debates mais recentes com status e total de turnos."""
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("""
                SELECT
                    c.id,
                    c.topic,
                    c.created_at,
                    COUNT(m.id) as total_turns,
                    MAX(m.status) as last_status
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT ?;
            """, (limit,))
            return [
                {
                    "id": r[0],
                    "topic": r[1],
                    "created_at": r[2],
                    "total_turns": r[3] or 0,
                    "last_status": r[4] or "N/A"
                }
                for r in rows
            ]

    @staticmethod
    async def get_debate_messages(conversation_id: str) -> List[Dict]:
        """Retorna todas as mensagens de um debate."""
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("""
                SELECT agent_name, content, status, turn
                FROM messages
                WHERE conversation_id = ?
                ORDER BY turn;
            """, (conversation_id,))
            return [
                {"agent": r[0], "content": r[1], "status": r[2], "turn": r[3]}
                for r in rows
            ]

    @staticmethod
    async def retrieve_knowledge(topic: str, limit: int = 5) -> List[Dict]:
        """Busca conhecimento relevante de debates anteriores sobre o topico.
        Tenta busca semantica primeiro; fallback para SQL LIKE."""
        # Tentar busca semantica primeiro
        try:
            from rag.semantic_search import SemanticSearch
            semantic = SemanticSearch()
            resultados = await semantic.buscar_argumentos_similares(topic, top_k=limit)
            if resultados:
                return [
                    {
                        "agent": r.get("agent_name", ""),
                        "content": r.get("content", ""),
                        "status": r.get("status", ""),
                        "topic": r.get("topic", topic),
                        "created_at": r.get("created_at", "")
                    }
                    for r in resultados
                ]
        except Exception as e:
            logger.debug(f"[RAG] Busca semantica falhou, usando fallback: {e}")

        # Fallback: SQL LIKE (sem filtro CONSENSUS)
        async with aiosqlite.connect(DB_PATH) as db:
            topic_words = [w for w in topic.split() if len(w) > 3]
            if not topic_words:
                topic_words = topic.split()
            like_conditions = " OR ".join(["c.topic LIKE ?" for _ in topic_words])
            like_params = [f"%{w}%" for w in topic_words]

            rows = await db.execute_fetchall(f"""
                SELECT DISTINCT
                    m.agent_name,
                    m.content,
                    m.status,
                    c.topic,
                    c.created_at
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE ({like_conditions})
                ORDER BY c.created_at DESC
                LIMIT ?;
            """, (*like_params, limit))
            return [
                {
                    "agent": r[0],
                    "content": r[1],
                    "status": r[2],
                    "topic": r[3],
                    "created_at": r[4]
                }
                for r in rows
            ]

    @staticmethod
    async def get_topic_history(topic: str) -> Dict:
        """Retorna historico de um topico especifico."""
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("""
                SELECT times_discussed, last_consensus, last_discussed_at
                FROM topic_memory
                WHERE topic = ?;
            """, (topic,))
            if rows:
                r = rows[0]
                return {
                    "times_discussed": r[0],
                    "last_consensus": r[1],
                    "last_discussed_at": r[2]
                }
            return None

    @staticmethod
    async def get_agent_contributions() -> Dict[str, Dict]:
        """Retorna contribuicoes de cada agente em debates anteriores."""
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall("""
                SELECT
                    agent_name,
                    COUNT(*) as total_messages,
                    SUM(CASE WHEN status = 'CONSENSUS' THEN 1 ELSE 0 END) as consensus_count
                FROM messages
                GROUP BY agent_name;
            """)
            return {
                r[0]: {"total": r[1], "consensus": r[2] or 0}
                for r in rows
            }

# =====================================================================
# 4. SESSAO - ARQUIVOS JSON
# =====================================================================

class SessionFiles:
    """Gerencia arquivos de sessao na pasta sessions/."""

    @staticmethod
    def get_session_dir(session_id: str) -> Path:
        now = datetime.now()
        date_dir = SESSIONS_DIR / now.strftime("%Y-%m-%d")
        time_dir = date_dir / now.strftime("%H-%M")
        session_dir = time_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    @staticmethod
    async def save_debate(session_dir: Path, debate_num: int, topic: str,
                          transcript: List[Dict], summary_short: str = None,
                          summary_full: str = None):
        debate_dir = session_dir / f"debate_{debate_num:03d}"
        debate_dir.mkdir(exist_ok=True)

        metadata = {
            "debate_num": debate_num,
            "topic": topic,
            "total_turns": len(transcript),
            "created_at": datetime.now().isoformat(),
            "agents": list(set(t["author"] for t in transcript)),
        }
        with open(debate_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        with open(debate_dir / "transcript.json", "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)

        summary_data = {}
        if summary_short:
            summary_data["summary_short"] = summary_short
        if summary_full:
            summary_data["summary_full"] = summary_full
        if summary_data:
            summary_data["created_at"] = datetime.now().isoformat()
            with open(debate_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump(summary_data, f, ensure_ascii=False, indent=2)

    @staticmethod
    async def save_session_summary(session_dir: Path, data: Dict):
        with open(session_dir / "nightly_summary.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    async def compact_old_sessions(sessions_dir: Path, days: int = 30):
        """Remove transcripts de sessoes antigas, mantendo summaries."""
        cutoff = datetime.now() - timedelta(days=days)
        compacted = 0

        if not sessions_dir.exists():
            return compacted

        for date_dir in sessions_dir.iterdir():
            if not date_dir.is_dir():
                continue

            for time_dir in date_dir.iterdir():
                if not time_dir.is_dir():
                    continue

                for session_dir in time_dir.iterdir():
                    if not session_dir.is_dir():
                        continue

                    # Verificar idade da sessao pelo nome (formato: YYYY-MM-DD_HH-MM)
                    try:
                        session_date_str = session_dir.name[:10]
                        session_date = datetime.strptime(session_date_str, "%Y-%m-%d")
                        if session_date >= cutoff:
                            continue
                    except (ValueError, IndexError):
                        continue

                    # Compactar cada debate
                    for debate_dir in session_dir.glob("debate_*"):
                        transcript_file = debate_dir / "transcript.json"
                        summary_file = debate_dir / "summary.json"

                        # So deleta se summary existe
                        if transcript_file.exists() and summary_file.exists():
                            transcript_file.unlink()

                            # Comprime metadata
                            metadata_file = debate_dir / "metadata.json"
                            if metadata_file.exists():
                                try:
                                    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
                                    metadata.pop("transcript_preview", None)
                                    metadata["compacted"] = True
                                    metadata["compacted_at"] = datetime.now().isoformat()
                                    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                                except Exception:
                                    pass

                            compacted += 1

        return compacted

# =====================================================================
# 5. GERACAO DE TOPICOS PELO OLLAMA
# =====================================================================

AGENT_DOMAINS = {
    "Arquiteto": "arquitetura de software",
    "SRE": "tolerancia a falhas e resiliencia",
    "DevOps": "CI/CD e infraestrutura",
    "DBA": "bancos de dados",
    "Security": "seguranca da informacao",
    "PO": "produto e valor de negocio",
    "Scrum Master": "processo e metodologias",
    "Gerente": "gestao de projetos e riscos",
}

RESPECT_RULES = (
    "\n\nREGRAS RIGOROSAS DE DEBATE:\n"
    "- Responda APENAS ao que foi dito nos turnos anteriores.\n"
    "- Nao interrompa. Aguarde sua vez.\n"
    "- Referencie explicitamente o argumento anterior quando contra-argumentar.\n"
    "- Nao repita o que ja foi dito. Traga novo valor.\n"
    "- SO discuta sobre: programacao, arquitetura, git, sistemas operacionais, "
    "lideranca tecnica, problemas humano-computador, devops, bancos de dados, seguranca.\n"
    "- Se o topico foger desses temas, responda que esta fora do escopo e de CONTINUE.\n"
    "- Nao seja condescendente: traga numeros, limites de hardware e impactos operacionais."
)

FALLBACK_TOPICS = [
    # Arquitetura
    "Microservicos vs Monolito: quando a complexidade nao compensa",
    "Event sourcing: quando vale a pena implementar?",
    "Domain-Driven Design: vale a pena em projetos pequenos?",
    "Arquitetura hexagonal: pratica ou teoria?",
    "Monolito modular: a melhor de ambos os mundos?",
    # DevOps
    "CI/CD com GitHub Actions vs GitLab CI: prós e contras",
    "Docker vs Podman: vale a pena trocar?",
    "Kubernetes: vale a pena para equipes pequenas?",
    "Infrastructure as Code: Terraform vs Pulumi",
    "GitOps: conceito vs realidade em empresas brasileiras",
    # Dados
    "Kafka vs RabbitMQ: qual fila de mensagens escolher?",
    "PostgreSQL vs MongoDB: quando o NoSQL nao e a resposta",
    "Cache invalidation: padroes eficazes em producao",
    "Banco de dados: conexoes, pooling e concorrencia",
    "Data lake vs data warehouse: qual arquitetura escolher?",
    # Seguranca
    "Seguranca em APIs: OAuth2, JWT e boas praticas",
    "Zero trust: conceito aplicado a empresas medias",
    "DevSecOps: como integrar seguranca no pipeline?",
    "Secret management: Vault, SSM ou solucoes caseiras?",
    "Container security: boas praticas para producao",
    # Git
    "Git flow vs trunk-based development: qual adotar?",
    "Code review eficaz: padroes e anti-patterns",
    "Conventional commits: vale a padronizacao?",
    "Monorepo vs polyrepo: fatores de decisao",
    "Git hooks: automatizar quality checks no commit",
    # Testes
    "Testes unitarios vs integracao: onde parar?",
    "TDD em 2026: ainda relevante ou obsoleto?",
    "Testes de contrato: Pact vs REST Assured",
    "E2E tests: Playwright vs Cypress vs Selenium",
    "Mutation testing: vale a pena no Brasil?",
    # Gestao e Processos
    "Squad autonomo: como evitar silos de conhecimento",
    "Migracao de legado: estrategias para sistemas criticos",
    "Tech debt: como medir e priorizar?",
    "1:1 eficaz: padroes para lideres tecnicos",
    "RFC tecnico: como escrever propostas de arquitetura?",
    # Observabilidade
    "Observabilidade: Grafana + Prometheus ou solucoes gerenciadas?",
    "Feature flags: como gerenciar releases sem dor de cabeca",
    "SLOs e SLIs: como definir metas de confiabilidade?",
    "OpenTelemetry: padrao ou mais uma ferramenta?",
    "Alert fatigue: como reduzir o ruido nos alertas?",
    # Cloud e Infra
    "Cloud AWS vs Azure vs GCP: fatores de decisao",
    "Multi-cloud: estrategia ou muleta?",
    "Serverless: quando realmente economiza?",
    "FinOps: como governar custos de cloud?",
    "Edge computing: casos de uso reais no Brasil",
    # Lideranca
    "Lideranca tecnica: ser promovido e continuar codando?",
    "Mentoria tecnica: como estruturar um programa?",
    "Burnout em tech: sinais e estrategias de prevencao",
    "Hiring tecnico: como avaliar soft skills?",
    "Onboarding de devs: boas praticas para squads",
    # Humano-Computador
    "UX em APIs: por que developer experience importa?",
    "Acessibilidade em software interno: por que ignorar?",
    "Produtividade remota: mitos e realidades em 2026",
    "Documentacao viva: como manter sem dor de cabeca?",
    "Fluxo de trabalho: quando o processo atrapalha?",
]

def is_too_similar(new_topic: str, recent_topics: List[str], threshold: float = 0.55) -> bool:
    """Verifica se o tópico é muito similar a qualquer um dos tópicos recentes."""
    from difflib import SequenceMatcher
    normalized_new = new_topic.lower().strip()
    for old_topic in recent_topics:
        similarity = SequenceMatcher(None, normalized_new, old_topic.lower().strip()).ratio()
        if similarity >= threshold:
            return True
    return False


async def generate_topic(model: str, history_topics: List[str]) -> str:
    """Pede ao Ollama para sugerir um topico de debate. Sempre gera novos topicos dinamicamente."""
    import random

    already = "\n".join(f"- {t}" for t in history_topics[-30:]) if history_topics else "Nenhum"

    prompt = (
        "Sugira UM topico de debate tecnico ORIGINAL e INTERESSANTE para engenheiros de software.\n"
        "Responda SOMENTE com o topico. Nao explique.\n"
        "Seja criativo - pense em topicos atuais, controversos, ou comparacoes nao obvias.\n"
        "IMPORTANTE: Varie a ESTRUTURA do topico. Nao use sempre o mesmo formato.\n"
        "Alterne entre: comparacoes diretas (X vs Y), perguntas, analises criticas,\n"
        "tendencias emergentes, decisoes de arquitetura, trade-offs, retrospectivas.\n"
        "Exemplos de bons topicos:\n"
        "- Kafka vs RabbitMQ para fila de eventos\n"
        "- Quando usar Redis ao inves de PostgreSQL\n"
        "- Git flow vs trunk-based development\n"
        "- AI pair programming: produtividade ou dependencia?\n"
        "- Microservicos: quando realmente precisa?\n"
        "- TypeScript e JavaScript: vale o trade-off?\n\n"
        f"Topicos ja discutidos (EVITE repetir e varie a estrutura):\n{already}\n\n"
        "Topico:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        "options": {"temperature": 0.9, "num_ctx": 1024}
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=90.0)
            resp.raise_for_status()
            raw = resp.json()["message"]["content"]

            try:
                data = json.loads(raw)
                topic = data.get("topic", "").strip()
            except json.JSONDecodeError:
                topic = raw.strip().strip('"').strip("'").strip()

            if 10 <= len(topic) <= 150 and not topic.startswith("{"):
                if is_too_similar(topic, history_topics[-30:]):
                    logger.warning(f"[TOPICOS] Similar demais: {topic[:60]}...")
                    if available := [t for t in FALLBACK_TOPICS
                                     if not is_too_similar(t, history_topics[-30:])]:
                        return random.choice(available)
                    return topic
                logger.info(f"[TOPICOS] Ollama: {topic}")
                return topic
            else:
                logger.warning(f"[TOPICOS] Invalido: {topic[:80]}...")
                if available := [t for t in FALLBACK_TOPICS
                                 if not is_too_similar(t, history_topics[-30:])]:
                    return random.choice(available)
                return random.choice(FALLBACK_TOPICS)

    except Exception as e:
        logger.error(f"[TOPICOS] Erro ao gerar: {e}")
        if available := [t for t in FALLBACK_TOPICS
                         if not is_too_similar(t, history_topics[-30:])]:
            return random.choice(available)
        return random.choice(FALLBACK_TOPICS)

async def generate_summary(model: str, topics: List[Dict]) -> str:
    """Gera resumo da sessao de debates."""
    topics_text = "\n".join(
        f"- {t['topic']} ({'consenso' if t['consensus'] else 'sem consenso'})"
        for t in topics
    )

    prompt = (
        "Gere um resumo executivo desta sessao de debate entre agentes de IA.\n"
        "Seja conciso. Inclua:\n"
        "1. Visao geral\n"
        "2. Topicos discutidos\n"
        "3. Consensos\n"
        "4. Divergencias\n\n"
        f"Topicos:\n{topics_text}\n\n"
        "Resumo:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 2048}
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=120.0)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Erro ao gerar resumo: {e}")
        return "Resumo nao disponivel."


async def generate_debate_summary(model: str, topic: str, history: List[Dict], consensus: bool) -> str:
    """Gera resumo conciso de um debate individual."""
    transcript = "\n".join(
        f"[{h['author']} - Turno {h['turn']}]: {h['content'][:200]}..."
        for h in history[-12:]  # Ultimos 12 turnos para caber no contexto
    )

    prompt = (
        "Gere um resumo CONCISO deste debate tecnico entre agentes de IA.\n"
        "Formato OBRIGATORIO (max 5 linhas):\n"
        "- Topico: ...\n"
        "- Posicoes principais: ... (2-3 pontos de cada lado)\n"
        "- Consenso: ... (ou 'Sem consenso' se houve divergencia)\n"
        "- Aprendizado chave: ... (1 insight principal)\n\n"
        f"Topico: {topic}\n"
        f"Resultado: {'Consenso' if consensus else 'Sem consenso'}\n"
        f"Turnos: {len(history)}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Resumo:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 2048}
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=90.0)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[SUMMARY] Erro ao gerar resumo do debate: {e}")
        return ""


async def generate_full_summary(model: str, topic: str, history: List[Dict],
                                 summary_short: str, consensus: bool) -> str:
    """Gera resumo completo preservando contexto situacional."""
    # Montar transcript completo (mais turnos que o resumo curto)
    transcript = "\n".join(
        f"[{h['author']} - Turno {h['turn']}]: {h['content'][:300]}"
        for h in history[-24:]  # Ultimos 24 turnos
    )

    prompt = (
        "Gere um RESUMO COMPLETO deste debate tecnico entre agentes de IA.\n"
        "Preserve o contexto situacional - tudo que aconteceu.\n\n"
        "Formato OBRIGATORIO:\n"
        "## Contexto\n"
        "- Por que este topico foi discutido\n"
        "- Problema ou decisao que motivou o debate\n\n"
        "## Posicoes Iniciais\n"
        "- Resumo da posicao de cada agente no inicio do debate\n\n"
        "## Evolucao do Debate\n"
        "- Como as posicoes mudaram ao longo dos turnos\n"
        "- Quais argumentos foram decisivos para mudar opinioes\n\n"
        "## Argumentos Decisivos\n"
        "- Top 3 argumentos mais importantes (com autor)\n"
        "- Por que foram importantes\n\n"
        "## Consenso ou Decisao\n"
        "- O que foi decidido (ou 'Sem consenso' se divergencia)\n"
        "- Principais pontos de acordo e desacordo\n\n"
        "## Aprendizados\n"
        "- Insights que devem ser lembrados para debates futuros\n"
        "- Conhecimento acumulado relevante\n\n"
        "## Proximos Passos\n"
        "- Implicacoes praticas\n"
        "- O que deve ser implementado ou investigado\n\n"
        f"Topico: {topic}\n"
        f"Resultado: {'Consenso' if consensus else 'Sem consenso'}\n"
        f"Total de turnos: {len(history)}\n"
        f"Resumo curto: {summary_short}\n\n"
        f"Transcript completo:\n{transcript}\n\n"
        "Resumo completo:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 4096}
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=120.0)
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[FULL-SUMMARY] Erro ao gerar resumo completo: {e}")
        return summary_short  # Fallback para resumo curto

# =====================================================================
# 6. AGENTES
# =====================================================================

# Modelos padrão por agente (podem ser sobrescritos via config)
DEFAULT_AGENT_MODELS = {
    "Arquiteto": None,   # Usa o modelo global
    "SRE": None,
    "DevOps": None,
    "DBA": None,
    "Security": None,
    "PO": None,
    "Scrum Master": None,
    "Gerente": None,
    "Dev Senior": None,
}


def create_agents(model: str, agent_models: dict = None) -> list:
    """Cria os 9 agentes com o modelo especificado.
    
    Args:
        model: Modelo padrão para todos os agentes
        agent_models: Dict opcional {nome_agente: modelo} para override por agente
    """
    configs = [
        ("Arquiteto", "Software Architect",
         "Voce e um arquiteto de software pragmatico focado em simplicidade, "
         "manutenibilidade e custo de infraestrutura (KISS / YAGNI). "
         "Defenda abordagens diretas e desafie complexidade acidental."),
        ("SRE", "Site Reliability Engineer",
         "Voce e um SRE focado em tolerancia a falhas, sistemas distribuidos, "
         "concorrencia, picos de carga e observabilidade. "
         "Identifique SPOF, locks de banco e gargalos de escalabilidade."),
        ("DevOps", "DevOps Engineer",
         "Voce e um DevOps focado em CI/CD, infraestrutura como codigo, "
         "automacao, containers e monitoramento. "
         "Question complexidade de pipelines e custos de infra."),
        ("DBA", "Database Specialist",
         "Voce e um especialista em bancos de dados focado em modelagem relacional, "
         "normalizacao, performance de queries, indexes e concorrencia. "
         "Question escolhas de NoSQL quando o problema e relacional."),
        ("Security", "Security Specialist",
         "Voce e um especialista em seguranca focado em vulnerabilidades, "
         "autenticacao, autorizacao e boas praticas. "
         "Aponte riscos de injecao, exposicao de dados e autenticacao fraca."),
        ("PO", "Product Owner",
         "Voce e um Product Owner focado em valor de negocio, ROI, "
         "priorizacao e alinhamento com objetivos estrategicos. "
         "Question se a solucao tecnica atende ao usuario final."),
        ("Scrum Master", "Scrum Master",
         "Voce e um Scrum Master focado em processo, impedimentos "
         "e fluxo de trabalho. Identifique gargalos de comunicacao."),
        ("Gerente", "Project Manager",
         "Voce e um Gerente de Projeto focado em prazo, recursos, "
         "riscos e orcamento. Aponte impacto em timeline e capacidade da equipe."),
        ("Dev Senior", "Senior Developer",
         "Voce e um desenvolvedor senior experiente focado em codigo limpo, "
         "padroes de design, SOLID, testes unitarios e boas praticas de programacao. "
         "Question code smells, gaps de testes e violacoes de principios SOLID."),
    ]

    agents = []
    for name, role, prompt in configs:
        # Usar modelo por agente se configurado, senão usar o global
        agent_model = (agent_models or {}).get(name) or model
        agent = type("AsyncAgent", (), {
            "name": name,
            "role_title": role,
            "system_prompt": (
                f"{prompt}\n\n"
                "DIRETIVAS OBRIGATORIAS:\n"
                "- Idioma: Responda EXCLUSIVAMENTE em Portugues do Brasil (pt-BR).\n"
                "  PROIBIDO: chines, japones, arabe, coreano, russo, ou qualquer idioma que nao seja portugues.\n"
                "  Se voce gerar texto em outro idioma, o debate sera ENCERRADO IMEDIATAMENTE.\n"
                "- Formato: Responda estritamente no esquema JSON com 'argument', 'status', 'question_to' e 'reasoning'.\n"
                "- RACIOCINIO: Preencha 'reasoning' com sua analise interna antes de responder.\n"
                "  Analise: 1) O que foi dito, 2) Dados concretos, 3) Se concorda com a maioria, 4) O que falta mencionar.\n"
                "- PERGUNTAS: Se tiver DUVIDA sobre argumento de outro agente, use 'question_to' com o nome dele.\n"
                "  Formato: question_to = 'NomeDoAgente'. O agente sera instruido a responder sua pergunta.\n"
                "- PLAGIO ABSOLUTAMENTE PROIBIDO: NAO copie, NAO repita, NAO parafraseie trechos de outros agentes.\n"
                "  Se voce copiar, o debate sera encerrado imediatamente.\n"
                "- ORIGINALIDADE: Traga argumentos COMPLETAMENTE NOVOS baseados na sua expertise.\n"
                "  Cada resposta deve conter ideias que NAO foram mencionadas por ninguem antes.\n"
                "- DADOS CONCRETOS: Traga numeros, metricas, exemplos reais, fonts especificas.\n"
                "- SUA ROLE: Fale APENAS sobre sua area de expertise. NAO discuta topicos de outros agentes.\n"
                "- CONSENSUS: Responda 'CONSENSUS' quando:\n"
                "  1) Voce concorda com a maioria dos pontos principais do debate\n"
                "  2) Os argumentos principais ja foram apresentados e discutidos\n"
                "  3) Nao ha objecoes criticas restantes\n"
                "  Nao e necessario concordar com TUDO. Basta concordar com o GERAL.\n"
                "  Se 3 ou mais agentes ja concordaram, considere seriamente CONSENSUS.\n"
                f"{RESPECT_RULES}"
            ),
            "model": agent_model,
        })()
        agents.append(agent)
    return agents

# =====================================================================
# 7. ORQUESTRADOR (FSM)
# =====================================================================

CONSENSUS_THRESHOLD = 4  # Maioria simples de 9 agentes para consenso

def _is_repetitive(arguments: list, threshold: float = 0.65) -> bool:
    """Detecta espiral de repeticao no debate.
    Verifica janelas de 3, 4 e 5 argumentos com threshold progressivo."""
    if len(arguments) < 5:
        return False

    # Normalizar argumentos
    normalized = [a.lower().strip() for a in arguments]

    # Verificar frases repetidas (primeiras 120 chars sao muito similares)
    for i in range(len(normalized) - 2):
        chunk = normalized[i][:120]
        for j in range(i + 1, len(normalized)):
            if normalized[j][:120] == chunk and chunk:
                return True

    # Verificar por palavras-chave repetidas (topicos principais)
    stop_words = {"o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
                  "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja"}

    def get_keywords(text):
        words = set(text.split()) - stop_words
        return words

    # Verificar janela de 5 argumentos
    if len(normalized) >= 5:
        last_5 = normalized[-5:]
        keywords_5 = [get_keywords(a) for a in last_5]
        all_kw = set().union(*keywords_5)
        common = keywords_5[0] & keywords_5[1] & keywords_5[2] & keywords_5[3] & keywords_5[4]
        if all_kw and len(common) / len(all_kw) > 0.55:
            return True

    # Verificar janela de 4 argumentos
    if len(normalized) >= 4:
        last_4 = normalized[-4:]
        keywords_4 = [get_keywords(a) for a in last_4]
        all_kw = set().union(*keywords_4)
        common = keywords_4[0] & keywords_4[1] & keywords_4[2] & keywords_4[3]
        if all_kw and len(common) / len(all_kw) > 0.6:
            return True

    # Verificar janela de 3 argumentos (original, mas mais flexivel)
    last_3 = normalized[-3:]
    keywords_3 = [get_keywords(a) for a in last_3]
    all_kw = set().union(*keywords_3)
    common = keywords_3[0] & keywords_3[1] & keywords_3[2]
    if all_kw and len(common) / len(all_kw) > threshold:
        return True

    return False


def _is_plagiarized(argument: str, history: list, threshold: float = 0.3) -> bool:
    """Detecta se um argumento contem trechos copiados de argumentos anteriores.
    Verifica frases de 12+ palavras E frases inteiras similares."""
    if not history or len(argument.split()) < 10:
        return False

    arg_lower = argument.lower().strip()
    history_lower = [h["content"].lower().strip() for h in history]

    # 1. Verificar n-gramas de 12 palavras (menos agressivo)
    arg_words = arg_lower.split()
    if len(arg_words) >= 12:
        ngram_size = 12
        for i in range(len(arg_words) - ngram_size + 1):
            ngram = " ".join(arg_words[i:i + ngram_size])
            for prev_arg in history_lower:
                if ngram in prev_arg:
                    return True

    # 2. Verificar frases inteiras (separadas por . ; ! ?)
    arg_sentences = [s.strip() for s in arg_lower.replace(";", ".").replace("!", ".").replace("?", ".").split(".") if len(s.strip()) > 20]
    for prev_arg in history_lower:
        prev_sentences = [s.strip() for s in prev_arg.replace(";", ".").replace("!", ".").replace("?", ".").split(".") if len(s.strip()) > 20]
        for arg_sent in arg_sentences:
            for prev_sent in prev_sentences:
                # Frase identical ou quase identical
                if arg_sent == prev_sent:
                    return True
                # 95% similar (substituicoes minimas)
                if len(arg_sent) > 30 and len(prev_sent) > 30:
                    words_a = set(arg_sent.split())
                    words_p = set(prev_sent.split())
                    if words_a and words_p:
                        overlap = len(words_a & words_p) / max(len(words_a), len(words_p))
                        if overlap > 0.95:
                            return True

    return False


def _is_valid_portuguese(text: str) -> bool:
    """Verifica se o texto esta em portugues (nao chines, arabe, etc)."""
    if not text or len(text) < 20:
        return True  # Textos curtos passam

    # Verificar caracteres nao-latinos (chines, japones, arabe, etc)
    non_latin = sum(1 for c in text if ord(c) > 0x2FFF and ord(c) < 0x10000)
    total = len(text)

    if total > 0:
        ratio = non_latin / total
        if ratio > 0.05:  # Mais de 5% caracteres nao-latinos
            return False

    # Verificar presenca de palavras comuns em portugues
    pt_words = {"de", "que", "nao", "uma", "por", "com", "para", "mais", "como", "mas",
                "foi", "são", "tem", "sao", "está", "isso", "este", "essa", "disso"}
    text_words = set(text.lower().split())
    pt_overlap = len(text_words & pt_words)

    # Se texto longo mas sem nenhuma palavra PT comum, suspeito
    if len(text.split()) > 30 and pt_overlap == 0:
        return False

    return True


class MultiAgentEngine:
    def __init__(self, agents: list, num_ctx: int = 8192, max_turns: int = 48,
                 min_turns: int = 2):
        self.agents = agents
        self.num_ctx = num_ctx
        self.max_turns = max_turns
        self.min_turns = min_turns
        # Modulos de estabilidade e RAG
        self.context_manager = ContextManager(num_ctx)
        self.loop_detector = LoopDetector()
        self.quality_monitor = QualityMonitor()
        self.semantic_search = SemanticSearch()

    async def execute_debate(self, conversation_id: str, topic: str, websocket: WebSocket,
                             session_id: str = None):
        await CortexDB.save_conversation(conversation_id, topic, session_id)
        history: List[Dict[str, str]] = []
        current_turn = 0
        consecutive_consensus = 0
        last_consensus = False

        # Recuperar conhecimento relevante de debates anteriores
        prior_knowledge = await CortexDB.retrieve_knowledge(topic, limit=3)
        topic_history = await CortexDB.get_topic_history(topic)

        # Verificar se topico ja foi discutido muitas vezes
        MAX_DISCUSSIONS = 5
        if topic_history and topic_history['times_discussed'] >= MAX_DISCUSSIONS:
            await websocket.send_json({
                "event": "debate_complete",
                "data": {
                    "reason": "topic_exhausted",
                    "total_turns": 0,
                    "message": f"Topico '{topic}' ja foi discutido {topic_history['times_discussed']} vezes. Tente um topico diferente."
                }
            })
            return False, "", ""

        # Construir contexto de conhecimento previo (RAG)
        knowledge_context = ""
        if prior_knowledge:
            knowledge_context = "\n\n## Conhecimento de Debates Anteriores:\n"
            for k in prior_knowledge:
                knowledge_context += f"- [{k['agent']}] sobre '{k['topic']}': {k['content'][:200]}...\n"
            knowledge_context += "\nUse esse conhecimento como base, mas nao repita os mesmos argumentos. Traga novas perspectivas.\n"

        if topic_history:
            knowledge_context += f"\n## Historico deste topico:\n"
            knowledge_context += f"- Discutido {topic_history['times_discussed']} vez(es) anteriormente\n"
            knowledge_context += f"- Ultimo resultado: {'Consenso' if topic_history['last_consensus'] else 'Sem consenso'}\n"
            knowledge_context += f"- Ultima discussao: {topic_history['last_discussed_at']}\n"

        # Carregar skills dos agentes para injetar no prompt
        try:
            all_agent_skills = await CortexDB.get_agent_skills()
        except Exception:
            all_agent_skills = {}

        # Lista de perguntas pendentes entre agentes
        pending_questions = []

        # Auto-expand num_ctx se necessario
        estimated_tokens = self.context_manager.estimate_tokens(topic) + 500  # overhead
        self.num_ctx = self.context_manager.auto_expand(estimated_tokens)

        # Health monitoring
        health = {"diversity_score": 1.0, "trend": "diverging", "repetition_count": 0, "plagiarism_count": 0}

        async with httpx.AsyncClient() as http_client:
            while current_turn < self.max_turns:
                for agent in self.agents:
                    current_turn += 1

                    await websocket.send_json({
                        "event": "turn_start",
                        "data": {"turn": current_turn, "agent": agent.name, "role": agent.role_title}
                    })

                    # Trunc inteligente do transcript
                    truncated_history = self.context_manager.truncate_intelligently(history, self.num_ctx - 1000)
                    transcript = [f"[{h['author']} - Turno {h['turn']}]: {h['content']}" for h in truncated_history]

                    if current_turn == 1:
                        instruction = (
                            "Voce abre o debate. Apresente sua tese tecnica inicial sobre o problema. "
                            "Se houver conhecimento previo relevante, use-o como ponto de partida, "
                            "mas traga novas perspectivas e dados atualizados."
                        )
                    else:
                        instruction = (
                            "Analise o argumento do turno anterior e responda de forma critica, "
                            "apontando pros/contras e trazendo dados concretos. "
                            "PROIBIDO COPIAR: NAO repita frases, NAO parafraseie, NAO use as mesmas palavras. "
                            "Traga uma analise COMPLETAMENTE NOVA com dados da sua area de expertise."
                        )

                    # Consenso forçado nos últimos turnos
                    turns_remaining = self.max_turns - current_turn
                    if turns_remaining <= 3 and current_turn >= self.min_turns:
                        instruction += (
                            "\n\nIMPORTANTE: O debate esta terminando. Se concordar com a maioria "
                            "dos pontos principais, responda CONSENSUS. Nao e necessario concordar com tudo."
                        )
                    elif current_turn > self.min_turns:
                        # Após min_turns, instruir a considerar consenso
                        consensus_count = sum(
                            1 for h in history[-9:]
                            if h.get("status") == "CONSENSUS"
                        )
                        if consensus_count >= 2:
                            instruction += (
                                f"\n\nNOTA: {consensus_count} agentes ja concordaram. "
                                "Se voce tambem concorda com os pontos principais, responda CONSENSUS."
                            )

                    # Knowledge context via RAG (substitui busca por substring)
                    try:
                        rag_context = await self.semantic_search.construir_knowledge_context(
                            topic, agent.name, history
                        )
                        if rag_context:
                            knowledge_context += rag_context
                    except Exception as e:
                        logger.debug(f"[RAG] Erro na busca semantica (ignorado): {e}")

                    # Quality feedback
                    instruction = self.quality_monitor.inject_quality_feedback(
                        health, agent.role_title, instruction
                    )

                    # Injetar skills do agente no contexto
                    agent_specific_context = knowledge_context
                    if agent.name in all_agent_skills:
                        skills = all_agent_skills[agent.name]
                        skills_text = "\n".join(
                            f"- {s['skill_domain']}: nivel {s['expertise_level']:.1f}"
                            for s in skills
                        )
                        agent_specific_context += f"\n\n## Suas areas de expertise (baseado em debates anteriores):\n{skills_text}\n"

                    # Injetar peso de voto do agente
                    vote_weight = await calculate_vote_weight(agent.name, all_agent_skills)
                    agent_specific_context += f"\n\nSeu peso de voto: {vote_weight:.1f} (baseado na sua expertise).\n"

                    # Pergunta pendente de outro agente
                    pending_question = next(
                        (q for q in pending_questions if q["to"] == agent.name),
                        None
                    )
                    if pending_question:
                        agent_specific_context += (
                            f"\n\n## PERGUNTA DE {pending_question['from']}:\n"
                            f"{pending_question['question']}\n"
                            f"Responda diretamente a essa pergunta. Se satisfatoria, considere CONSENSUS.\n"
                        )

                    user_prompt = (
                        f"Topico da Discusao: {topic}\n\n"
                        f"Historico:\n" + ("\n".join(transcript) if transcript else "Inicio do debate.") +
                        f"\n\n{agent_specific_context}\n"
                        f"\n{instruction}\n"
                        f"Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' quando concordar com a maioria dos pontos principais.\n"
                        f"IMPORTANTE: Apos {self.min_turns} turnos, se voce concorda com o geral, digite CONSENSUS."
                    )

                    payload = {
                        "model": agent.model,
                        "messages": [
                            {"role": "system", "content": agent.system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "format": AgentDecision.model_json_schema(),
                        "options": {
                            "temperature": 0.5,
                            "repeat_penalty": 1.15,
                            "num_ctx": self.num_ctx
                        }
                    }

                    try:
                        resp = await http_client.post(OLLAMA_CHAT_URL, json=payload, timeout=180.0)
                        resp.raise_for_status()
                        raw_json = resp.json()["message"]["content"]
                        decision = AgentDecision(**json.loads(raw_json))

                        # Retry se texto nao for portugues (max 1 tentativa)
                        if not _is_valid_portuguese(decision.argument):
                            logger.warning(f"[LANGUAGE] Turno {current_turn} ({agent.name}): texto nao-portugues, retry...")
                            retry_prompt = (
                                f"{user_prompt}\n\n"
                                "!!! ATENCAO: Sua ultima resposta foi em CHINES ou outro idioma invalido. !!!\n"
                                "!!! RESPONDA APENAS EM PORTUGUES DO BRASIL! !!!\n"
                                "!!! NAO USE CARACTERES CHINESES, JAPONESES, OU ARABES! !!!"
                            )
                            retry_payload = {
                                "model": agent.model,
                                "messages": [
                                    {"role": "system", "content": agent.system_prompt + "\n\n!!! RESPONDA APENAS EM PORTUGUES! NUNCA USE CHINES! !!!"},
                                    {"role": "user", "content": retry_prompt}
                                ],
                                "stream": False,
                                "format": AgentDecision.model_json_schema(),
                                "options": {
                                    "temperature": 0.3,
                                    "repeat_penalty": 1.15,
                                    "num_ctx": self.num_ctx
                                }
                            }
                            try:
                                retry_resp = await http_client.post(OLLAMA_CHAT_URL, json=retry_payload, timeout=180.0)
                                retry_resp.raise_for_status()
                                retry_json = retry_resp.json()["message"]["content"]
                                retry_decision = AgentDecision(**json.loads(retry_json))
                                if _is_valid_portuguese(retry_decision.argument):
                                    decision = retry_decision
                                    logger.info(f"[LANGUAGE] Turno {current_turn} ({agent.name}): retry bem-sucedido")
                                else:
                                    logger.warning(f"[LANGUAGE] Turno {current_turn} ({agent.name}): retry tambem falhou")
                            except Exception as retry_e:
                                logger.error(f"[LANGUAGE] Turno {current_turn} ({agent.name}): erro no retry: {retry_e}")

                    except Exception as e:
                        logger.error(f"Erro turno {current_turn} ({agent.name}): {e}")
                        decision = AgentDecision(
                            argument=f"Falha de inferencia no agente {agent.name}.",
                            status="CONTINUE"
                        )

                    effective_status = decision.status
                    if current_turn < self.min_turns and effective_status == "CONSENSUS":
                        effective_status = "CONTINUE"

                    # Deteccao de repeticao do LLM (so apos 5+ argumentos)
                    if len(history) >= 5:
                        recent_args = [h["content"] for h in history[-5:]]
                        if _is_repetitive(recent_args):
                            effective_status = "FORCE_STOP"
                            logger.info(f"[REPETITION] Turno {current_turn}: espiral de repeticao detectada")

                    # Deteccao de plagio
                    if len(history) >= 1 and _is_plagiarized(decision.argument, history):
                        effective_status = "FORCE_STOP"
                        logger.info(f"[PLAGIARISM] Turno {current_turn}: trechos copiados detectados")

                    # Validacao de idioma (rejeitar chines, arabe, etc)
                    if not _is_valid_portuguese(decision.argument):
                        effective_status = "FORCE_STOP"
                        logger.info(f"[LANGUAGE] Turno {current_turn}: texto nao-portugues detectado")

                    # Health monitoring (loop detector)
                    health = self.loop_detector.analyze_debate_health(history)
                    if self.loop_detector.should_end_debate(health, current_turn, self.min_turns):
                        effective_status = "FORCE_STOP"
                        logger.info(f"[HEALTH] Turno {current_turn}: {health['recommendation']} (diversity={health['diversity_score']:.2f})")

                    # Quality monitoring
                    quality = self.quality_monitor.monitor_argument_quality(
                        decision.argument, history, agent.role_title
                    )
                    if quality.get("is_too_short"):
                        logger.info(f"[QUALITY] Turno {current_turn}: argumento muito curto ({quality['word_count']} palavras)")

                    # Persistir scores de qualidade
                    try:
                        msg_id = str(uuid.uuid4())
                        await CortexDB.save_argument_score(
                            message_id=msg_id,
                            conversation_id=conversation_id,
                            agent_name=agent.name,
                            quality_score=quality.get("novelty_score", 0.5),
                            novelty_score=quality.get("novelty_score", 0.5),
                            expertise_alignment=quality.get("expertise_alignment", 0.5),
                            overall_score=quality.get("overall_score", 0.5)
                        )
                    except Exception:
                        pass

                    # Rejeitar argumentos de baixa qualidade (apos min_turns)
                    if quality.get("overall_score", 1.0) < 0.2 and current_turn > self.min_turns:
                        effective_status = "CONTINUE"
                        logger.info(f"[QUALITY] Turno {current_turn}: argumento rejeitado (score={quality.get('overall_score', 0):.2f})")

                    await CortexDB.save_message(
                        conversation_id, agent.name, decision.argument, effective_status, current_turn
                    )
                    history.append({"author": agent.name, "content": decision.argument, "turn": current_turn})

                    # Processar pergunta para outro agente
                    if decision.question_to and decision.question_to != agent.name:
                        pending_questions.append({
                            "from": agent.name,
                            "to": decision.question_to,
                            "question": decision.argument,
                            "turn": current_turn
                        })
                        logger.info(f"[QUESTION] Turno {current_turn}: {agent.name} perguntou para {decision.question_to}")

                    # Auto-indexar embedding da mensagem (RAG) - apenas a cada 10 turnos
                    if current_turn % 10 == 0:
                        try:
                            await self.semantic_search.indexar_argumentos_pendentes()
                        except Exception:
                            pass  # Non-critical

                    # Atualizar skills do agente se contribuiu para consenso
                    if effective_status == "CONSENSUS":
                        try:
                            await CortexDB.update_agent_skills(agent.name, topic, True)
                        except Exception:
                            pass

                    # Auto-salvar estado do debate a cada 5 turnos
                    if current_turn % 5 == 0:
                        try:
                            await CortexDB.save_debate_state(
                                conversation_id, topic, current_turn, history, "active", session_id
                            )
                        except Exception:
                            pass

                    await websocket.send_json({
                        "event": "turn_end",
                        "data": {
                            "turn": current_turn,
                            "agent": agent.name,
                            "role": agent.role_title,
                            "argument": decision.argument,
                            "status": effective_status
                        }
                    })

                    if effective_status == "CONSENSUS":
                        consecutive_consensus += 1
                        last_consensus = True
                    elif effective_status == "FORCE_STOP":
                        # FORCE_STOP: sistema forcou parada, encerrar debate
                        logger.info(f"[FORCE_STOP] Turno {current_turn}: debate encerrado por sistema")
                        summary_short = await generate_debate_summary(
                            self.agents[0].model, topic, history, False
                        )
                        summary_full = await generate_full_summary(
                            self.agents[0].model, topic, history, summary_short, False
                        )
                        await websocket.send_json({
                            "event": "debate_complete",
                            "data": {
                                "reason": "force_stop",
                                "total_turns": current_turn,
                                "summary": summary_short,
                                "summary_full": summary_full
                            }
                        })
                        return False, summary_short, summary_full
                    else:
                        consecutive_consensus = 0
                        last_consensus = False

                    if consecutive_consensus >= CONSENSUS_THRESHOLD and current_turn >= self.min_turns:
                        # Verificar se consenso requer aprovação humana
                        topic_context = {"times_discussed": topic_history.get("times_discussed", 0) if topic_history else 0}
                        needs_human = await requires_human_approval(ActionType.CONSENSUS, topic_context)

                        if needs_human:
                            # Enviar evento de validação humana
                            await websocket.send_json({
                                "event": "human_validation_required",
                                "data": {
                                    "type": "consensus_reached",
                                    "topic": topic,
                                    "total_turns": current_turn,
                                    "message": "Consenso atingido. Aguardando aprovação do humano para finalizar."
                                }
                            })
                            # Aguardar resposta do humano (timeout 60s)
                            try:
                                import asyncio
                                response = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
                                if not response.get("approved", False):
                                    # Humano rejeitou — continuar debate
                                    consecutive_consensus = 0
                                    last_consensus = False
                                    logger.info(f"[HUMAN] Turno {current_turn}: consenso rejeitado pelo humano")
                                    continue
                            except (asyncio.TimeoutError, Exception):
                                # Timeout ou erro — continuar debate
                                consecutive_consensus = 0
                                last_consensus = False
                                logger.info(f"[HUMAN] Turno {current_turn}: timeout na validação humana")

                        # Gerar resumos do debate
                        summary_short = await generate_debate_summary(
                            self.agents[0].model, topic, history, True
                        )
                        summary_full = await generate_full_summary(
                            self.agents[0].model, topic, history, summary_short, True
                        )
                        await websocket.send_json({
                            "event": "debate_complete",
                            "data": {
                                "reason": "consensus",
                                "total_turns": current_turn,
                                "summary": summary_short,
                                "summary_full": summary_full
                            }
                        })
                        return last_consensus, summary_short, summary_full

                    if current_turn >= self.max_turns:
                        break

        # Gerar resumos do debate (timeout)
        summary_short = await generate_debate_summary(
            self.agents[0].model, topic, history, last_consensus
        )
        summary_full = await generate_full_summary(
            self.agents[0].model, topic, history, summary_short, last_consensus
        )
        await websocket.send_json({
            "event": "debate_complete",
            "data": {
                "reason": "max_turns_reached",
                "total_turns": current_turn,
                "summary": summary_short,
                "summary_full": summary_full
            }
        })
        return last_consensus, summary_short, summary_full

# =====================================================================
# 8. FASTAPI + WEBSOCKET
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    SESSIONS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    await CortexDB.init()

    # Compacta sessoes antigas no startup
    compacted = await SessionFiles.compact_old_sessions(SESSIONS_DIR, days=30)
    if compacted > 0:
        logger.info(f"[STARTUP] {compacted} transcripts compactados (sessoes >30 dias)")

    logger.info("[STARTUP] THz Room iniciado com sucesso")
    yield
    # Shutdown gracioso
    logger.info("[SHUTDOWN] Encerrando THz Room...")
    await shutdown_manager.save_current_state()
    logger.info("[SHUTDOWN] Dados salvos. Ate logo!")

app = FastAPI(title="THz Room - Multi-Agent Autonomous Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

async def _get_transcript(conversation_id: str) -> list:
    """Busca transcript de um debate no banco."""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT agent_name, content, status, turn FROM messages WHERE conversation_id = ? ORDER BY turn;",
            (conversation_id,)
        )
        return [{"author": r[0], "content": r[1], "status": r[2], "turn": r[3]} for r in rows]

# Set para rastrear requests ativos (idempotencia)
_active_requests: set = set()


@app.post("/api/debate/{conversation_id}/pause")
async def pause_debate(conversation_id: str):
    """Pausa um debate ativo, salvando seu estado."""
    state = await CortexDB.get_debate_state(conversation_id)
    if not state:
        return {"error": "Debate nao encontrado"}
    if state["status"] == "completed":
        return {"error": "Debate ja foi finalizado"}

    await CortexDB.save_debate_state(
        conversation_id, state["topic"], state["current_turn"],
        state["history"], "paused", state.get("session_id")
    )
    return {"status": "paused", "conversation_id": conversation_id, "turn": state["current_turn"]}


@app.post("/api/debate/{conversation_id}/resume")
async def resume_debate(conversation_id: str):
    """Retoma um debate pausado."""
    state = await CortexDB.get_debate_state(conversation_id)
    if not state:
        return {"error": "Debate nao encontrado"}
    if state["status"] != "paused":
        return {"error": "Debate nao esta pausado"}

    return {
        "status": "resumed",
        "conversation_id": conversation_id,
        "topic": state["topic"],
        "current_turn": state["current_turn"],
        "history": state["history"],
        "session_id": state.get("session_id")
    }


@app.get("/api/debate/{conversation_id}/state")
async def get_debate_state(conversation_id: str):
    """Retorna o estado atual de um debate."""
    state = await CortexDB.get_debate_state(conversation_id)
    if not state:
        return {"error": "Debate nao encontrado"}
    return state


@app.get("/api/models")
async def list_models():
    """Lista modelos disponíveis no Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:11434/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = resp.json().get("models", [])
            return {"models": [m["name"] for m in models]}
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.get("/api/agents/config")
async def get_agent_config():
    """Retorna configuração de modelos por agente."""
    return {"agent_models": DEFAULT_AGENT_MODELS}


# =====================================================================
# GUARDRAILS, SCENARIOS & TEAMWORK REST API
# =====================================================================

@app.post("/api/guardrails/validate")
async def validate_guardrail(payload: dict):
    """Valida se um tópico ou texto obedece ao Guardrail de Escopo Técnico."""
    text = payload.get("text", "") or payload.get("topic", "")
    res = get_scope_guard().validate_topic(text)
    return res.dict()


@app.get("/api/scenarios/engineering")
async def get_engineering_scenario():
    """Retorna um cenário rico de engenharia com restrições de produção."""
    engine = get_scenario_engine()
    sc = engine.get_random_engineering_scenario()
    return sc.dict()


@app.get("/api/scenarios/content")
async def get_content_scenario():
    """Retorna um tema de artigo técnico aprofundado."""
    engine = get_scenario_engine()
    topic = engine.get_random_content_topic()
    return {"topic": topic}


@app.post("/api/teamwork/start")
async def start_teamwork_session(req: TeamworkSessionRequest):
    """Inicia uma sessão autônoma de TeamWork (Engenharia ou Conteúdo)."""
    scope_res = get_scope_guard().validate_topic(req.goal)
    if not scope_res.allowed:
        raise HTTPException(status_code=400, detail=f"Guardrail de Escopo: {scope_res.reason}")

    model = await resolve_model(req.model)
    req.model = model

    if req.mode == TeamworkMode.ENGINEERING:
        pipeline = EngineeringPipeline(model=model, num_ctx=req.num_ctx)
        result = await pipeline.run(req)
    elif req.mode == TeamworkMode.CONTENT:
        pipeline = ContentPipeline(model=model, num_ctx=req.num_ctx)
        result = await pipeline.run(req)
    else:
        raise HTTPException(status_code=400, detail=f"Modo de Teamwork '{req.mode}' inválido.")

    await CortexDB.save_teamwork_session(
        session_id=result.session_id,
        project_name=result.project_name,
        mode=result.mode.value if hasattr(result.mode, "value") else str(result.mode),
        goal=result.goal,
        output_dir=result.output_directory,
        executive_summary=result.executive_summary,
        total_steps=result.total_steps,
        artifacts=[a.dict() for a in result.artifacts]
    )
    return result.dict()


@app.post("/api/teamwork/stream")
async def stream_teamwork_session(req: TeamworkSessionRequest):
    """Executa a pipeline de TeamWork e transmite os eventos em tempo real via SSE."""
    scope_res = get_scope_guard().validate_topic(req.goal)
    if not scope_res.allowed:
        raise HTTPException(status_code=400, detail=f"Guardrail de Escopo: {scope_res.reason}")

    model = await resolve_model(req.model)
    req.model = model

    queue = asyncio.Queue()

    async def event_callback(evt_data):
        await queue.put(evt_data)

    async def run_pipeline():
        try:
            if req.mode == TeamworkMode.ENGINEERING:
                pipeline = EngineeringPipeline(model=model, num_ctx=req.num_ctx)
                res = await pipeline.run(req, progress_callback=event_callback)
            else:
                pipeline = ContentPipeline(model=model, num_ctx=req.num_ctx)
                res = await pipeline.run(req, progress_callback=event_callback)

            await CortexDB.save_teamwork_session(
                session_id=res.session_id,
                project_name=res.project_name,
                mode=res.mode.value if hasattr(res.mode, "value") else str(res.mode),
                goal=res.goal,
                output_dir=res.output_directory,
                executive_summary=res.executive_summary,
                total_steps=res.total_steps,
                artifacts=[a.dict() for a in res.artifacts]
            )

            await queue.put({"type": "teamwork_complete", "status": "completed", "result": res.dict()})
        except Exception as e:
            await queue.put({"type": "error", "status": "error", "message": str(e)})
        finally:
            await queue.put(None)

    asyncio.create_task(run_pipeline())

    async def sse_gen():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(sse_gen(), media_type="text/event-stream")


@app.get("/api/teamwork/projects")
async def list_teamwork_projects():
    """Retorna a lista unificada de projetos com metadados do CortexDB e disco."""
    db_projects = await CortexDB.get_recent_teamwork_sessions(50)
    disk_projects = WorkspaceManager.get_all_projects_summary()

    # Combinar projetos do banco com diretórios do disco
    seen_ids = set()
    unified = []
    for p in db_projects:
        seen_ids.add(p["project_name"])
        seen_ids.add(p["session_id"])
        unified.append(p)

    for dp in disk_projects:
        if dp["project_id"] not in seen_ids:
            unified.append({
                "session_id": dp["project_id"],
                "project_name": dp["project_id"],
                "mode": "engineering" if "project_eng" in dp["project_id"] else "content",
                "goal": dp["project_id"].replace("_", " "),
                "status": "completed",
                "output_dir": dp["path"],
                "executive_summary": f"Projeto em disco com {dp['total_files']} arquivo(s).",
                "total_steps": dp["total_files"],
                "created_at": dp["created_at"],
                "files": dp["files"],
                "total_files": dp["total_files"]
            })

    return {"projects": unified, "total": len(unified)}


@app.get("/api/teamwork/file")
async def read_project_file(project_id: str, file_path: str):
    """Lê o conteúdo de um arquivo de projeto de forma segura dentro do Sandbox."""
    try:
        from guardrails.sandbox import PathValidator
        target = PathValidator.validate_safe_write_path(file_path, project_id)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
        content = target.read_text(encoding="utf-8")
        return {"project_id": project_id, "file_path": file_path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/teamwork/workspace/{project_id}")
async def get_workspace_files(project_id: str):
    """Lista todos os arquivos gerados de um projeto no disco."""
    files = WorkspaceManager.get_project_tree(project_id)
    return {"project_id": project_id, "files": files, "total_files": len(files)}


# =====================================================================
# OPENAI-COMPATIBLE API LAYER (/v1)
# =====================================================================

@app.get("/v1/models")
async def openai_list_models():
    """Retorna a lista de modelos suportados no formato OpenAI."""
    models_list = [
        {"id": "thz-teamwork:engineering", "object": "model", "created": 1700000000, "owned_by": "thz-minds"},
        {"id": "thz-teamwork:content", "object": "model", "created": 1700000000, "owned_by": "thz-minds"},
        {"id": "thz-council:debate", "object": "model", "created": 1700000000, "owned_by": "thz-minds"},
        {"id": "thz-lang:copilot", "object": "model", "created": 1700000000, "owned_by": "thz-minds"},
    ]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                for m in resp.json().get("models", []):
                    models_list.append({
                        "id": m["name"],
                        "object": "model",
                        "created": int(datetime.now().timestamp()),
                        "owned_by": "ollama"
                    })
    except Exception:
        pass
    return {"object": "list", "data": models_list}


@app.post("/v1/chat/completions")
async def openai_chat_completions(req: Request):
    """Endpoint compatível com OpenAI para integração com Thz-Lang, VS Code, Cursor e IDEs."""
    try:
        body = await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    model = body.get("model", "thz-teamwork:engineering")
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    if not messages:
        raise HTTPException(status_code=400, detail="Campo 'messages' é obrigatório")

    user_prompt = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_prompt = m.get("content", "")
            break
    if not user_prompt:
        user_prompt = messages[-1].get("content", "")

    guard = get_scope_guard()
    scope_val = guard.validate_topic(user_prompt)
    if not scope_val.allowed:
        raise HTTPException(status_code=400, detail=f"Guardrail de Escopo: {scope_val.reason}")

    if "engineering" in model or "thz-lang" in model:
        pipeline = EngineeringPipeline()
        team_req = TeamworkSessionRequest(goal=user_prompt, mode=TeamworkMode.ENGINEERING)

        if stream:
            async def sse_gen():
                created = int(datetime.now().timestamp())
                cmpl_id = "chatcmpl-" + uuid.uuid4().hex
                yield f"data: {json.dumps({'id': cmpl_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'delta': {'role': 'assistant', 'content': '🚀 Iniciando pipeline de engenharia THZ Minds...\n\n'}, 'index': 0, 'finish_reason': None}]})}\n\n"

                res = await pipeline.run(team_req)

                final_content = (
                    f"### 📦 Projeto Gerado: {res.project_name}\n\n"
                    f"{res.executive_summary}\n\n"
                    f"**Arquivos Gravados em:** `{res.output_directory}`\n\n"
                    f"**Arquivos Gerados:**\n" + "\n".join(f"- `{a.path}` ({a.author_role})" for a in res.artifacts)
                )
                yield f"data: {json.dumps({'id': cmpl_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'delta': {'content': final_content}, 'index': 0, 'finish_reason': 'stop'}]})}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse_gen(), media_type="text/event-stream")
        else:
            res = await pipeline.run(team_req)
            content_resp = (
                f"### 🚀 Solução de Engenharia: {res.project_name}\n\n"
                f"{res.executive_summary}\n\n"
                f"**Arquivos Gravados em:** `{res.output_directory}`\n\n"
                f"**Arquivos Gerados ({len(res.artifacts)}):**\n" + "\n".join(f"- `{a.path}` ({a.author_role})" for a in res.artifacts)
            )
            return {
                "id": "chatcmpl-" + uuid.uuid4().hex,
                "object": "chat.completion",
                "created": int(datetime.now().timestamp()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": content_resp},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": len(user_prompt)//4, "completion_tokens": len(content_resp)//4, "total_tokens": (len(user_prompt)+len(content_resp))//4}
            }

    elif "content" in model:
        pipeline = ContentPipeline()
        team_req = TeamworkSessionRequest(goal=user_prompt, mode=TeamworkMode.CONTENT)
        res = await pipeline.run(team_req)
        content_resp = (
            f"### ✍️ Artigo Técnico Concluído: {res.project_name}\n\n"
            f"{res.executive_summary}\n\n"
            f"**Salvo em:** `{res.output_directory}`\n\n"
            f"**Arquivos Gerados ({len(res.artifacts)}):**\n" + "\n".join(f"- `{a.path}` ({a.author_role})" for a in res.artifacts)
        )
        return {
            "id": "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(datetime.now().timestamp()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content_resp},
                "finish_reason": "stop"
            }],
            "usage": {"prompt_tokens": len(user_prompt)//4, "completion_tokens": len(content_resp)//4, "total_tokens": (len(user_prompt)+len(content_resp))//4}
        }

    else:
        resolved = await resolve_model(model)
        payload = {"model": resolved, "messages": messages, "stream": stream}
        async with httpx.AsyncClient() as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload, timeout=120.0)
            if resp.status_code == 200:
                return resp.json()
            raise HTTPException(status_code=resp.status_code, detail=resp.text)


@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        raw_payload = await websocket.receive_json()

        # Idempotencia: verificar request_id duplicado
        request_id = raw_payload.get("request_id") or str(uuid.uuid4())
        if request_id in _active_requests:
            await websocket.send_json({
                "event": "error",
                "data": {"message": "Request duplicado detectado"}
            })
            return
        _active_requests.add(request_id)

        mode = raw_payload.get("mode", "single")

        if mode == "single":
            req = SingleDebateRequest(**raw_payload)
            # Validação pelo Guardrail de Escopo Técnico
            scope_val = get_scope_guard().validate_topic(req.topic)
            if not scope_val.allowed:
                await websocket.send_json({
                    "event": "error",
                    "data": {"message": f"Bloqueado pelo Guardrail: {scope_val.reason}"}
                })
                return

            model = await resolve_model(req.model)
            agents = create_agents(model)
            engine = MultiAgentEngine(agents=agents, num_ctx=req.num_ctx, max_turns=req.max_turns)

            conv_id = str(uuid.uuid4())
            logger.info(f"[SINGLE] Topico: {req.topic[:60]} | Modelo: {model}")
            consensus, summary_short, summary_full = await engine.execute_debate(conv_id, req.topic, websocket)
            await CortexDB.update_topic_memory(req.topic, consensus)
            await CortexDB.update_conversation_summary(conv_id, summary_short, summary_full)

        elif mode == "autonomous":
            req = AutonomousSessionRequest(**raw_payload)
            model = await resolve_model(req.model)
            session_id = datetime.now().strftime("%Y-%m-%d_%H-%M")
            session_dir = SessionFiles.get_session_dir(session_id)

            await websocket.send_json({
                "event": "session_start",
                "data": {
                    "session_id": session_id,
                    "duration_hours": req.duration_hours,
                    "model": model
                }
            })

            start_time = datetime.now()
            end_time = start_time + timedelta(hours=req.duration_hours)
            debate_count = 0
            topics_used = []

            # Registra sessao atual para shutdown gracioso
            shutdown_manager.current_session = {
                "id": session_id,
                "start_time": start_time.isoformat(),
                "duration": req.duration_hours,
                "debate_count": 0,
                "topics": []
            }

            while datetime.now() < end_time and not shutdown_manager.should_exit:
                history_topics = await CortexDB.get_discussed_topics()
                # Extrair topicos strings de topics_used (que contem dicts)
                used_topic_strings = [t["topic"] if isinstance(t, dict) else t for t in topics_used]
                topic = await generate_topic(model, history_topics + used_topic_strings)
                debate_count += 1

                # Atualiza estado para shutdown
                shutdown_manager.current_session["debate_count"] = debate_count
                shutdown_manager.current_session["topics"] = topics_used

                await websocket.send_json({
                    "event": "debate_start",
                    "data": {"debate_num": debate_count, "topic": topic}
                })

                conv_id = str(uuid.uuid4())
                agents = create_agents(model)
                engine = MultiAgentEngine(agents=agents, num_ctx=req.num_ctx, max_turns=req.max_turns)
                consensus, summary_short, summary_full = await engine.execute_debate(conv_id, topic, websocket, session_id)

                topics_used.append({"topic": topic, "consensus": consensus})
                await CortexDB.update_topic_memory(topic, consensus)
                await CortexDB.update_conversation_summary(conv_id, summary_short, summary_full)

                # Salva transcript do debate
                transcript = await _get_transcript(conv_id)
                await SessionFiles.save_debate(session_dir, debate_count, topic, transcript, summary_short, summary_full)

                if datetime.now() + timedelta(minutes=10) < end_time and not shutdown_manager.should_exit:
                    logger.info(f"[PAUSA] 30 segundos antes do proximo debate...")
                    await websocket.send_json({
                        "event": "debate_paused",
                        "data": {"duration_seconds": 30, "next_debate": debate_count + 1}
                    })
                    await asyncio.sleep(30)

            # Limpa shutdown manager
            shutdown_manager.current_session = None

            summary_text = await generate_summary(model, topics_used)
            summary_data = {
                "session_id": session_id,
                "total_debates": debate_count,
                "duration_hours": req.duration_hours,
                "topics": topics_used,
                "summary": summary_text,
                "created_at": datetime.now().isoformat()
            }
            await SessionFiles.save_session_summary(session_dir, summary_data)

            await websocket.send_json({
                "event": "session_complete",
                "data": {
                    "session_id": session_id,
                    "total_debates": debate_count,
                    "duration_hours": req.duration_hours,
                    "topics": [t["topic"] for t in topics_used],
                    "summary": summary_text
                }
            })

            logger.info(f"[SESSION] Encerrada. {debate_count} debates. Resumo salvo em {session_dir}")

        else:
            await websocket.send_json({
                "event": "error",
                "data": {"message": f"Modo invalido: {mode}. Use 'single' ou 'autonomous'."}
            })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"Erro WebSocket: {exc}")
    finally:
        _active_requests.discard(request_id)
        try:
            await websocket.close()
        except RuntimeError:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
