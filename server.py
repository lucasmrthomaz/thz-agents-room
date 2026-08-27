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
    status: Literal["CONTINUE", "CONSENSUS"] = Field(
        description="CONTINUE para manter a discusao; CONSENSUS apenas em caso de acordo total."
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
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
            """)
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
                CREATE TABLE IF NOT EXISTS content_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    reference_type TEXT NOT NULL,
                    reference_key TEXT NOT NULL,
                    reference_summary TEXT NOT NULL,
                    relevance_score REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
            """)
            await db.commit()
            logger.info(f"Cortex DB inicializado: {DB_PATH}")

    @staticmethod
    async def save_conversation(conversation_id: str, topic: str, session_id: str = None):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO conversations (id, topic, session_id) VALUES (?, ?, ?);",
                (conversation_id, topic, session_id)
            )
            await db.commit()

    @staticmethod
    async def save_message(conversation_id: str, agent_name: str, content: str, status: str, turn: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO messages (conversation_id, agent_name, content, status, turn) VALUES (?, ?, ?, ?, ?);",
                (conversation_id, agent_name, content, status, turn)
            )
            await db.commit()

    @staticmethod
    async def update_topic_memory(topic: str, consensus: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            existing = await db.execute_fetchall(
                "SELECT id, times_discussed FROM topic_memory WHERE topic = ?;", (topic,)
            )
            if existing:
                row = existing[0]
                new_count = row[1] + 1
                await db.execute(
                    "UPDATE topic_memory SET times_discussed = ?, last_consensus = ?, last_discussed_at = CURRENT_TIMESTAMP WHERE id = ?;",
                    (new_count, consensus, row[0])
                )
            else:
                await db.execute(
                    "INSERT INTO topic_memory (topic, last_consensus, last_discussed_at) VALUES (?, ?, CURRENT_TIMESTAMP);",
                    (topic, consensus)
                )
            await db.commit()

    @staticmethod
    async def update_agent_skills(agent_name: str, domain: str, contributed_to_consensus: bool):
        async with aiosqlite.connect(DB_PATH) as db:
            existing = await db.execute_fetchall(
                "SELECT id, times_applied, consensus_contributions FROM agent_skills WHERE agent_name = ? AND skill_domain = ?;",
                (agent_name, domain)
            )
            if existing:
                row = existing[0]
                new_applied = row[1] + 1
                new_consensus = row[2] + (1 if contributed_to_consensus else 0)
                new_level = min(1.0, new_consensus / max(new_applied, 1))
                await db.execute(
                    "UPDATE agent_skills SET times_applied = ?, consensus_contributions = ?, expertise_level = ? WHERE id = ?;",
                    (new_applied, new_consensus, new_level, row[0])
                )
            else:
                await db.execute(
                    "INSERT INTO agent_skills (agent_name, skill_domain, times_applied, consensus_contributions, expertise_level) VALUES (?, ?, 1, ?, ?);",
                    (agent_name, domain, 1 if contributed_to_consensus else 0, 1.0 if contributed_to_consensus else 0.0)
                )
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
                          transcript: List[Dict], summary: str = None):
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

        if summary:
            with open(debate_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump({"summary": summary}, f, ensure_ascii=False, indent=2)

    @staticmethod
    async def save_session_summary(session_dir: Path, data: Dict):
        with open(session_dir / "nightly_summary.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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

# =====================================================================
# 6. AGENTES
# =====================================================================

def create_agents(model: str) -> list:
    """Cria os 8 agentes com o modelo especificado."""
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
                "- Formato: Responda estritamente no esquema JSON com 'argument' e 'status'.\n"
                f"{RESPECT_RULES}"
            ),
            "model": model,
        })()
        agents.append(agent)
    return agents

# =====================================================================
# 7. ORQUESTRADOR (FSM)
# =====================================================================

def _is_repetitive(arguments: list, threshold: float = 0.8) -> bool:
    """Detecta se 3 argumentos sao muito similares (repeticao do LLM)."""
    if len(arguments) < 3:
        return False
    last_3 = [a.lower().strip() for a in arguments[-3:]]
    words = [set(arg.split()) for arg in last_3]
    intersection = words[0] & words[1] & words[2]
    union = words[0] | words[1] | words[2]
    if not union:
        return False
    return len(intersection) / len(union) > threshold


class MultiAgentEngine:
    def __init__(self, agents: list, num_ctx: int = 8192, max_turns: int = 48,
                 min_turns: int = 3):
        self.agents = agents
        self.num_ctx = num_ctx
        self.max_turns = max_turns
        self.min_turns = min_turns

    async def execute_debate(self, conversation_id: str, topic: str, websocket: WebSocket,
                             session_id: str = None):
        await CortexDB.save_conversation(conversation_id, topic, session_id)
        history: List[Dict[str, str]] = []
        current_turn = 0
        consecutive_consensus = 0
        last_consensus = False

        async with httpx.AsyncClient() as http_client:
            while current_turn < self.max_turns:
                for agent in self.agents:
                    current_turn += 1

                    await websocket.send_json({
                        "event": "turn_start",
                        "data": {"turn": current_turn, "agent": agent.name, "role": agent.role_title}
                    })

                    transcript = [f"[{h['author']} - Turno {h['turn']}]: {h['content']}" for h in history]

                    if current_turn == 1:
                        instruction = "Voce abre o debate. Apresente sua tese tecnica inicial sobre o problema."
                    else:
                        instruction = (
                            "Analise o argumento do turno anterior e responda de forma critica, "
                            "apontando pros/contras e trazendo dados concretos."
                        )

                    user_prompt = (
                        f"Topico da Discusao: {topic}\n\n"
                        f"Historico:\n" + ("\n".join(transcript) if transcript else "Inicio do debate.") +
                        f"\n\n{instruction}\n"
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
                        recent_args = [h["content"] for h in history[-3:]]
                        if _is_repetitive(recent_args):
                            effective_status = "CONSENSUS"
                            logger.info(f"[REPETITION] Turno {current_turn}: 3 argumentos similares detectados")

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
                    else:
                        consecutive_consensus = 0
                        last_consensus = False

                    if consecutive_consensus >= len(self.agents) and current_turn >= self.min_turns:
                        await websocket.send_json({
                            "event": "debate_complete",
                            "data": {"reason": "consensus", "total_turns": current_turn}
                        })
                        return last_consensus

                    if current_turn >= self.max_turns:
                        break

        await websocket.send_json({
            "event": "debate_complete",
            "data": {"reason": "max_turns_reached", "total_turns": current_turn}
        })
        return last_consensus

# =====================================================================
# 8. FASTAPI + WEBSOCKET
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    SESSIONS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    await CortexDB.init()
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

@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        raw_payload = await websocket.receive_json()

        mode = raw_payload.get("mode", "single")

        if mode == "single":
            req = SingleDebateRequest(**raw_payload)
            model = await resolve_model(req.model)
            agents = create_agents(model)
            engine = MultiAgentEngine(agents=agents, num_ctx=req.num_ctx, max_turns=req.max_turns)

            conv_id = str(uuid.uuid4())
            logger.info(f"[SINGLE] Topico: {req.topic[:60]} | Modelo: {model}")
            await engine.execute_debate(conv_id, req.topic, websocket)
            await CortexDB.update_topic_memory(req.topic, True)

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
                consensus = await engine.execute_debate(conv_id, topic, websocket, session_id)

                topics_used.append({"topic": topic, "consensus": consensus})
                await CortexDB.update_topic_memory(topic, consensus)

                # Salva transcript do debate
                transcript = await _get_transcript(conv_id)
                await SessionFiles.save_debate(session_dir, debate_count, topic, transcript, summary=None)

                if datetime.now() + timedelta(minutes=10) < end_time and not shutdown_manager.should_exit:
                    logger.info(f"[PAUSA] 10 minutos antes do proximo debate...")
                    await asyncio.sleep(600)

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
        try:
            await websocket.close()
        except RuntimeError:
            pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
