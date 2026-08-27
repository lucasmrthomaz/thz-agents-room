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
from typing import Dict, List, Literal, Optional

import aiosqlite
import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Modulos de estabilidade e RAG
from stability.context_manager import ContextManager
from stability.loop_detector import LoopDetector
from stability.quality_monitor import QualityMonitor
from rag.semantic_search import SemanticSearch

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

class AgentDecision(BaseModel):
    argument: str = Field(
        description="Argumento tecnico detalhado em Portugues do Brasil (pt-BR)."
    )
    status: Literal["CONTINUE", "CONSENSUS", "FORCE_STOP"] = Field(
        description="CONTINUE para manter a discusao; CONSENSUS apenas em caso de acordo total; FORCE_STOP quando o sistema forca parada."
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
    """Consulta Ollama e retorna o modelo recomendado (qwen2.5:7b ou menor)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            if not models:
                return DEFAULT_MODEL

            # Prioriza qwen2.5:7b se disponivel
            for m in models:
                name = m.get("name", "")
                if "qwen2.5:7b" in name or name == "qwen2.5:7b":
                    logger.info(f"Modelo encontrado: {name}")
                    return name

            # Se nao tem 7b, pega o menor disponivel
            smallest = min(models, key=lambda m: m.get("size", 0))
            name = smallest["name"]
            logger.info(f"Modelo fallback (menor): {name}")
            return name

    except Exception as e:
        logger.warning(f"Falha ao descobrir modelos: {e}. Usando default: {DEFAULT_MODEL}")
        return DEFAULT_MODEL

async def resolve_model(requested: Optional[str]) -> str:
    if requested:
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
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_agent ON argument_embeddings(agent_name);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_topic ON argument_embeddings(topic);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_emb_message ON argument_embeddings(message_id);")
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
        Retorna os argumentos mais relevantes de debates passados."""
        async with aiosqlite.connect(DB_PATH) as db:
            # Busca debates com topicos similares (LIKE)
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
                AND m.status = 'CONSENSUS'
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

# Limite maximo de topicos antes de considerar esgotados
MAX_TOPICS_WITHOUT_REPEAT = 50

async def generate_topic(model: str, history_topics: List[str]) -> Optional[str]:
    """Pede ao Ollama para sugerir um topico de debate. Retorna None se topicos esgotados."""
    import random

    # Verifica se topicos estao esgotados
    if len(history_topics) >= MAX_TOPICS_WITHOUT_REPEAT:
        logger.warning(f"[TOPICOS] Esgotados! {len(history_topics)} topicos ja discutidos.")
        return None

    # Se ja tem muitos topicos, mistura fallback com geracao
    if len(history_topics) >= 20:
        used = set(history_topics[-30:])
        available = [t for t in FALLBACK_TOPICS if t not in used]
        if available:
            topic = random.choice(available)
            logger.info(f"[TOPICOS] Fallback: {topic}")
            return topic
        # Todos os fallbacks usados, tenta gerar novos
        pass

    already = "\n".join(f"- {t}" for t in history_topics[-20:]) if history_topics else "Nenhum"

    prompt = (
        "Sugira UM topico de debate tecnico para engenheiros de software.\n"
        "Responda SOMENTE com o topico. Nao explique.\n"
        "Exemplos de bons topicos:\n"
        "- Kafka vs RabbitMQ para fila de eventos\n"
        "- Quando usar Redis ao inves de PostgreSQL\n"
        "- Git flow vs trunk-based development\n\n"
        f"Topicos ja usados:\n{already}\n\n"
        "Topico:"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        "options": {"temperature": 0.7, "num_ctx": 1024}
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
                logger.info(f"[TOPICOS] Ollama: {topic}")
                return topic
            else:
                logger.warning(f"[TOPICOS] Invalido: {topic[:80]}...")
                if available := [t for t in FALLBACK_TOPICS if t not in set(history_topics[-30:])]:
                    return random.choice(available)
                return random.choice(FALLBACK_TOPICS)

    except Exception as e:
        logger.error(f"[TOPICOS] Erro ao gerar: {e}")
        if available := [t for t in FALLBACK_TOPICS if t not in set(history_topics[-30:])]:
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

def create_agents(model: str) -> list:
    """Cria os 9 agentes com o modelo especificado."""
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
        agent = type("AsyncAgent", (), {
            "name": name,
            "role_title": role,
            "system_prompt": (
                f"{prompt}\n\n"
                "DIRETIVAS OBRIGATORIAS:\n"
                "- Idioma: Responda EXCLUSIVAMENTE em Portugues do Brasil (pt-BR).\n"
                "  PROIBIDO: chines, japones, arabe, coreano, russo, ou qualquer idioma que nao seja portugues.\n"
                "  Se voce gerar texto em outro idioma, o debate sera ENCERRADO IMEDIATAMENTE.\n"
                "- Formato: Responda estritamente no esquema JSON com 'argument' e 'status'.\n"
                "- PLAGIO ABSOLUTAMENTE PROIBIDO: NAO copie, NAO repita, NAO parafraseie trechos de outros agentes.\n"
                "  Se voce copiar, o debate sera encerrado imediatamente.\n"
                "- ORIGINALIDADE: Traga argumentos COMPLETAMENTE NOVOS baseados na sua expertise.\n"
                "  Cada resposta deve conter ideias que NAO foram mencionadas por ninguem antes.\n"
                "- DADOS CONCRETOS: Traga numeros, metricas, exemplos reais, fonts especificas.\n"
                "- SUA ROLE: Fale APENAS sobre sua area de expertise. NAO discuta topicos de outros agentes.\n"
                f"{RESPECT_RULES}"
            ),
            "model": model,
        })()
        agents.append(agent)
    return agents

# =====================================================================
# 7. ORQUESTRADOR (FSM)
# =====================================================================

def _is_repetitive(arguments: list, threshold: float = 0.6) -> bool:
    """Detecta espiral de repeticao no debate.
    Verifica janelas de 3, 4 e 5 argumentos com threshold progressivo."""
    if len(arguments) < 3:
        return False

    # Normalizar argumentos
    normalized = [a.lower().strip() for a in arguments]

    # Verificar frases repetidas (primeiras 50 chars sao muito similares)
    for i in range(len(normalized) - 2):
        chunk = normalized[i][:50]
        for j in range(i + 1, len(normalized)):
            if normalized[j][:50] == chunk and chunk:
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
        if all_kw and len(common) / len(all_kw) > 0.5:
            return True

    # Verificar janela de 4 argumentos
    if len(normalized) >= 4:
        last_4 = normalized[-4:]
        keywords_4 = [get_keywords(a) for a in last_4]
        all_kw = set().union(*keywords_4)
        common = keywords_4[0] & keywords_4[1] & keywords_4[2] & keywords_4[3]
        if all_kw and len(common) / len(all_kw) > 0.55:
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
    Verifica frases de 8+ palavras E frases inteiras similares."""
    if not history or len(argument.split()) < 10:
        return False

    arg_lower = argument.lower().strip()
    history_lower = [h["content"].lower().strip() for h in history]

    # 1. Verificar n-gramas de 8 palavras (mais agressivo)
    arg_words = arg_lower.split()
    if len(arg_words) >= 8:
        ngram_size = 8
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
                # 90% similar (substituicoes minimas)
                if len(arg_sent) > 30 and len(prev_sent) > 30:
                    words_a = set(arg_sent.split())
                    words_p = set(prev_sent.split())
                    if words_a and words_p:
                        overlap = len(words_a & words_p) / max(len(words_a), len(words_p))
                        if overlap > 0.9:
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
                 min_turns: int = 3):
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
            return

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

                    user_prompt = (
                        f"Topico da Discusao: {topic}\n\n"
                        f"Historico:\n" + ("\n".join(transcript) if transcript else "Inicio do debate.") +
                        f"\n\n{knowledge_context}\n"
                        f"\n{instruction}\n"
                        f"Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' apenas se houver concordancia total."
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

                    # Deteccao de repeticao do LLM
                    if len(history) >= 3:
                        recent_args = [h["content"] for h in history[-5:]] if len(history) >= 5 else [h["content"] for h in history[-3:]]
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

                    await CortexDB.save_message(
                        conversation_id, agent.name, decision.argument, effective_status, current_turn
                    )
                    history.append({"author": agent.name, "content": decision.argument, "turn": current_turn})

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

                    if consecutive_consensus >= len(self.agents) and current_turn >= self.min_turns:
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
                topic = await generate_topic(model, history_topics + topics_used)
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
                    logger.info(f"[PAUSA] 1 minuto antes do proximo debate...")
                    await websocket.send_json({
                        "event": "debate_paused",
                        "data": {"duration_seconds": 60, "next_debate": debate_count + 1}
                    })
                    await asyncio.sleep(60)

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
