# Plano: Idempotencia + Resumos + Compactacao

**Data:** 2026-08-27
**Status:** Aprovado

---

## 1. Analise de Idempotencia

| Area | Risco | Problema |
|------|-------|----------|
| `messages` table | **CRITICAL** | Sem UNIQUE constraint, INSERT cego |
| `topic_memory` upsert | **HIGH** | Read-then-write nao atomico |
| `agent_skills` upsert | **HIGH** | Read-then-write nao atomico |
| Single mode consensus bug | **HIGH** | Sempre passa `True` (linha 1202) |
| WebSocket request dedup | **HIGH** | Sem dedup de payloads |
| `__history__` sentinel bug | **MEDIUM** | Envia debate fake ao servidor |
| `conversations` table | LOW | Sem retry safety |
| `debate_health` dead schema | LOW | Tabela criada mas nao usada |
| `content_references` dead schema | LOW | Tabela criada mas nao usada |

---

## 2. Implementacao - Nivel Banco de Dados

### 2.1 Tabela `messages` (CRITICAL)

```sql
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
```

Mudanca em `CortexDB.save_message()`:
```python
idempotency_key = f"{conversation_id}:{turn}:{agent_name}"
await db.execute(
    "INSERT OR IGNORE INTO messages (...) VALUES (?, ?, ?, ?, ?, ?);",
    (..., idempotency_key)
)
```

### 2.2 Tabela `conversations`

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    session_id TEXT,
    summary_short TEXT,
    summary_full TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

Mudanca em `CortexDB.save_conversation()`:
```python
await db.execute(
    "INSERT OR IGNORE INTO conversations (...) VALUES (?, ?, ?, ?, ?);",
    (...)
)
```

### 2.3 Upserts Atomicos

`update_topic_memory()`:
```python
await db.execute("""
    INSERT INTO topic_memory (topic, last_consensus, last_discussed_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(topic) DO UPDATE SET
        times_discussed = times_discussed + 1,
        last_consensus = excluded.last_consensus,
        last_discussed_at = CURRENT_TIMESTAMP;
""", (topic, consensus))
```

`update_agent_skills()`:
```python
await db.execute("""
    INSERT INTO agent_skills (agent_name, skill_domain, times_applied,
                             consensus_contributions, expertise_level)
    VALUES (?, ?, 1, ?, ?)
    ON CONFLICT(agent_name, skill_domain) DO UPDATE SET
        times_applied = times_applied + 1,
        consensus_contributions = consensus_contributions + excluded.consensus_contributions,
        expertise_level = MIN(1.0, expertise_level + 0.1);
""", (agent_name, domain, 1 if consensus else 0, 0.1 if consensus else 0.0))
```

### 2.4 Cleanup Tabelas Mortas

- `debate_health` — Remover
- `content_references` — Remover

---

## 3. Implementacao - Nivel Aplicacao

### 3.1 Request Dedup (server.py)

```python
_active_requests: Set[str] = set()

@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket):
    ...
    request_id = raw_payload.get("request_id") or str(uuid.uuid4())

    if request_id in _active_requests:
        await websocket.send_json({"event": "error", "data": {"message": "Duplicate request"}})
        return

    _active_requests.add(request_id)
    try:
        # ... processar debate
    finally:
        _active_requests.discard(request_id)
```

### 3.2 Client Request ID (gui.py, client.py)

```python
payload["request_id"] = str(uuid.uuid4())
```

### 3.3 Bug Fix: Single Mode Consensus

```python
# ANTES (BUG):
await engine.execute_debate(conv_id, req.topic, websocket)
await CortexDB.update_topic_memory(req.topic, True)  # Always True!

# DEPOIS:
consensus = await engine.execute_debate(conv_id, req.topic, websocket)
await CortexDB.update_topic_memory(req.topic, consensus)
```

### 3.4 Bug Fix: `__history__` Sentinel

Remover o send WebSocket falso, usar DB direto.

---

## 4. Resumos (Completo + Curto)

### 4.1 Schema

```sql
ALTER TABLE conversations ADD COLUMN summary_short TEXT;
ALTER TABLE conversations ADD COLUMN summary_full TEXT;
```

### 4.2 Nova Funcao: `generate_full_summary()`

Gera resumo completo preservando contexto situacional:
- Contexto do debate
- Posicoes iniciais de cada agente
- Evolucao das posicoes
- Argumentos decisivos
- Consenso/decisao
- Aprendizados
- Proximos passos

### 4.3 Fluxo

```
execute_debate()
    ↓
generate_debate_summary() → summary_short
generate_full_summary()   → summary_full
    ↓
    ├──→ SQLite: conversations.summary_short + summary_full
    ├──→ Arquivo: debate_NNN/summary.json
    └──→ WebSocket → GUI/CLI
```

---

## 5. Compactacao Fisica

### 5.1 Novo Metodo: `SessionFiles.compact_old_sessions()`

Remove transcripts de sessoes antigas (>30 dias), mantendo summaries.

### 5.2 Trigger Automatico

Chamar no startup (lifespan) e periodicamente.

---

## 6. Documentacao

### README.md

- Adicionar features: Idempotencia, Resumo Completo, Compactacao
- Atualizar tabela de banco de dados

### docs/ROADMAP.md

- Secao 8: Idempotencia
- Secao 9: Resumos
- Secao 10: Compactacao

---

## 7. Testes

| Arquivo | Testes |
|---------|--------|
| `test_db.py` | Idempotency key, upserts atomicos, summary columns |
| `test_session_files.py` | compact_old_sessions, summary salvo |
| `test_integration.py` | Request dedup, consensus fix |
| `test_client.py` | Request ID no payload |

---

## 8. Resumo das Mudancas

| Arquivo | Mudancas |
|---------|----------|
| `server.py` | Schema (2 colunas + idempotency_key), upserts atomicos, request dedup, generate_full_summary(), compact_old_sessions(), bug fixes |
| `gui.py` | Request ID no payload |
| `client.py` | Request ID, remover bug __history__ |
| `tests/test_db.py` | Testes de idempotencia e summary |
| `tests/test_session_files.py` | Testes de compactacao |
| `README.md` | Features, banco de dados |
| `docs/ROADMAP.md` | Novas secoes 8-10 |
| `docs/TODO.md` | Limpar tarefas pendentes |
