-- MALE - Schema SQLite (compativel com thz-room-cortex.db do Python)

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    session_id TEXT,
    summary_short TEXT,
    summary_full TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS topic_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL UNIQUE,
    category TEXT,
    times_discussed INTEGER DEFAULT 1,
    last_consensus BOOLEAN,
    last_discussed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS debate_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,
    description TEXT,
    example_data TEXT,
    success_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS argument_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE,
    agent_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS knowledge_graph (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_topic TEXT NOT NULL,
    target_topic TEXT NOT NULL,
    relationship TEXT DEFAULT 'similar',
    strength REAL DEFAULT 0.8,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS teamwork_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    author_role TEXT,
    content_length INTEGER,
    artifact_uuid TEXT,
    sha256_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indices
CREATE INDEX IF NOT EXISTS idx_emb_agent ON argument_embeddings(agent_name);
CREATE INDEX IF NOT EXISTS idx_emb_topic ON argument_embeddings(topic);
CREATE INDEX IF NOT EXISTS idx_emb_message ON argument_embeddings(message_id);
CREATE INDEX IF NOT EXISTS idx_kg_source ON knowledge_graph(source_topic);
CREATE INDEX IF NOT EXISTS idx_kg_target ON knowledge_graph(target_topic);
CREATE INDEX IF NOT EXISTS idx_tw_session ON teamwork_artifacts(session_id);
