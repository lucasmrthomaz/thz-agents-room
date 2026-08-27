# THZ Minds — Roadmap de Evolucao

## Visao Geral

Este documento documenta as otimizacoes de performance, fine-tuning, embeddings/RAG e estrategias de estabilidade implementadas no THZ Minds.

**Data:** 2026-08-27
**Status:** Em implementacao

---

## 1. Otimizacoes de Performance (Ja Implementadas)

### 1.1 WAL Mode Per-Connection
- **Problema:** PRAGMA `journal_mode=WAL` so era executado no `init()`. Cada nova conexao perdia o WAL.
- **Solucao:** Helper `get_db()` configura PRAGMAs em cada conexao.
- **Impacto:** Escrita 2-5x mais rapida, concorrencia melhorada.

### 1.2 Connection Pooling
- **Problema:** Cada operacao DB abria/fechava conexao SQLite.
- **Solucao:** Conexao unica reutilizavel no `CortexDB`.
- **Impacto:** Reducao de overhead de socket por turno.

### 1.3 Deteccao de Repeticao Melhorada
- **Problema:** Algoritmo original so verificava 3 argumentos com threshold 0.8.
- **Solucao:** Janela progressiva (3/4/5 argumentos), threshold 0.6, stop words, frases identicas.
- **Impacto:** Detecta espirais lentas e rapidas.

### 1.4 Deteccao de Plagio
- **Problema:** Agentes copiavam trechos longos uns dos outros.
- **Solucao:** `_is_plagiarized()` — n-gramas de 15 palavras contra historico.
- **Impacto:** Forca originalidade nos argumentos.

### 1.5 Conhecimento Previo
- **Problema:** Debates se repetiam sem base de conhecimento.
- **Solucao:** `retrieve_knowledge()` injeta contexto de debates anteriores no prompt.
- **Impacto:** Agentes constroem sobre entendimento previo.

### 1.6 Protecao contra Topicos Exauridos
- **Problema:** Mesmos topicos eram discutidos indefinidamente.
- **Solucao:** MAX_DISCUSSIONS=5 — rejeita topicos discutidos 5+ vezes.
- **Impacto:** Forca diversidade de topicos.

### 1.7 Pausa Corrigida (10min -> 1min)
- **Problema:** Pausa entre debates era 10 minutos (lento).
- **Solucao:** Reduzido para 1 minuto (60s) com countdown na GUI.
- **Impacto:** Sessoes autonomous mais produtivas.

---

## 2. Fine-tuning QLoRA por Agente

### 2.1 Hardware Constraints (RTX 4060 8GB)

| Parametro | Valor | Justificativa |
|-----------|-------|---------------|
| VRAM budget | ~6.5GB | Reserva 1.5GB para sistema |
| Quantizacao | 4-bit NF4 | Minimo para 7B caber |
| LoRA rank | 8 | Reduzido para economizar VRAM |
| LoRA alpha | 16 | 2x rank |
| Target modules | q_proj, k_proj, v_proj, o_proj | Apenas attention |
| Batch size | 1 | Minimo absoluto |
| Gradient accumulation | 8 | Effective batch = 8 |
| Sequence length | 1024 | Limitado para caber na VRAM |
| Gradient checkpointing | Obrigatorio | Economiza ~40% VRAM |
| Optimizer | paged_adamw_8bit | Minimo overhead |

### 2.2 Pipeline de Exportacao

```
server.py -> export_dataset.py -> ShareGPT JSONL -> train_qlora.py -> GGUF -> Ollama
```

**Formato ShareGPT:**
```json
{
  "conversations": [
    {"from": "system", "value": "{system_prompt}"},
    {"from": "human", "value": "Topico: {topic}\nHistorico: {transcript}"},
    {"from": "gpt", "value": "{\"argument\": \"...\", \"status\": \"CONTINUE\"}"}
  ]
}
```

**Filtragem de qualidade:**
- Apenas debates com 8+ turnos
- Remover argumentos <50 palavras
- Remover debates com plagio detectado
- Priorizar argumentos CONSENSUS
- Max 1000 exemplos por agente

### 2.3 Stack de Treinamento

| Componente | Ferramenta |
|------------|------------|
| Fine-tuning | Unsloth + QLoRA |
| Base model | Qwen 2.5 7B Instruct |
| Quantizacao | bitsandbytes NF4 |
| Training | TRL SFTTrainer |
| Export | llama.cpp GGUF q4_k_m |
| Deploy | Modelfile + ollama create |

### 2.4 Arquivos

| Arquivo | Descricao |
|---------|-----------|
| `training/export_dataset.py` | Exporta dados SQLite para ShareGPT JSONL |
| `training/train_qlora.py` | Script de treinamento QLoRA |
| `training/deploy_to_ollama.py` | Merge + GGUF + Modelfile + ollama create |
| `training/config.yaml` | Hiperparametros por agente |
| `training/quality_filter.py` | Filtragem de dados de treinamento |

---

## 3. Embeddings + RAG

### 3.1 Arquitetura

```
Debate Turn -> Embed (nomic-embed-text) -> Store (sqlite-vec) -> Retrieve (cosine) -> Inject Context
```

### 3.2 Modelo de Embeddings

**Recomendado:** `nomic-embed-text` (Ollama-native, 768-dim)

**Alternativa pt-BR:** `Colibri` (~157M params, 0.650 MTEB-BR)

### 3.3 Schema SQLite

```sql
CREATE TABLE argument_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL UNIQUE,
    agent_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);
```

### 3.4 Arquivos

| Arquivo | Descricao |
|---------|-----------|
| `rag/__init__.py` | Pacote RAG |
| `rag/embedder.py` | Gerenciamento de embeddings |
| `rag/vector_store.py` | sqlite-vec wrapper |
| `rag/semantic_search.py` | Busca semantica + context builder |
| `rag/index_embeddings.py` | Script de indexacao batch |
| `rag/migrate_db.py` | Adicionar tabela argument_embeddings |

---

## 4. Estabilidade da Sessao

### 4.1 Context Window Management

- **Auto-expand num_ctx:** Detecta overflow e aumenta automaticamente (max 32768)
- **Trunc inteligente:** Mantem primeiro turno + ultimos 5, remove meio

### 4.2 Anti-Loop Detection

- **Diversity score:** Mede quao diferentes sao os argumentos (0.0-1.0)
- **Trend analysis:** "diverging" | "converging" | "stagnant"
- **Auto-end:** Se diversity < 0.3 por 3 turnos → force_consensus

### 4.3 Quality Maintenance

- **Word count:** Minimo 50 palavras por argumento
- **Novelty score:** Verifica se argumento e novo (nao repete)
- **Expertise alignment:** Verifica se argumento esta alinhado com a role do agente
- **Quality feedback:** Injeta instrucoes de melhoria no prompt

### 4.4 Arquivos

| Arquivo | Descricao |
|---------|-----------|
| `stability/__init__.py` | Pacote estabilidade |
| `stability/context_manager.py` | Auto-expand num_ctx + trunc inteligente |
| `stability/loop_detector.py` | Anti-loop avancado + health monitoring |
| `stability/quality_monitor.py` | Quality check + feedback injection |

---

## 5. Dependencias

```
# Adicionar ao requirements.txt:
unsloth>=2024.0
bitsandbytes>=0.43.0
trl>=0.8.0
peft>=0.13.0
sentence-transformers>=3.0
sqlite-vec>=0.1.0
aiofiles>=24.0
```

---

## 6. Sequencia de Implementacao

| Fase | Descricao | Status |
|------|-----------|--------|
| 1 | Database schema + sqlite-vec | Concluido |
| 2 | Embeddings + RAG | Concluido |
| 3 | Semantic search | Concluido |
| 4 | Context manager | Concluido |
| 5 | Anti-loop detector | Concluido |
| 6 | Quality monitor | Concluido |
| 7 | Integracao no server.py | Concluido |
| 8 | Export dataset | Concluido |
| 9 | Train script | Concluido |
| 10 | Deploy script | Concluido |
| 11 | Idempotencia | Concluido |
| 12 | Resumos (curto + completo) | Concluido |
| 13 | Compactacao de sessoes | Concluido |

---

## 7. Metricas de Sucesso

| Metrica | Target |
|---------|--------|
| Velocidade geral | 20-40% mais rapido |
| Transcripts completos | Sem truncamento silencioso |
| Deteccao de plagio | <5% falsos positivos |
| Busca semantica | Top-5 relevantes em <100ms |
| Fine-tuning | 7B model em 8GB VRAM |
| Qualidade dos argumentos | Diversity score > 0.5 |

---

## 8. Idempotencia

### 8.1 Nivel Banco de Dados

**Tabela `messages`:**
- `idempotency_key TEXT UNIQUE` — Chave composta: `conversation_id:turn:agent_name`
- `INSERT OR IGNORE` — Rejeita duplicatas silenciosamente

**Tabela `conversations`:**
- `INSERT OR IGNORE` — Retry seguro

**Upserts atomicos:**
- `topic_memory`: `INSERT ... ON CONFLICT(topic) DO UPDATE SET times_discussed = times_discussed + 1`
- `agent_skills`: `INSERT ... ON CONFLICT(agent_name, skill_domain) DO UPDATE SET times_applied = times_applied + 1`

### 8.2 Nivel Aplicacao

**Request dedup no WebSocket:**
- `_active_requests: set` — Rastreia requests ativos
- `request_id` no payload — Identificador unico por request
- Verificacao antes de processar — Rejeita duplicatas

**Client request ID:**
- GUI e CLI adicionam `request_id` ao payload
- Previne debates duplicados por reconexao

### 8.3 Bug Fixes

- **Single mode consensus**: Agora usa return value real de `execute_debate()`
- **__history__ sentinel**: Removido envio falso ao servidor

---

## 9. Resumos

### 9.1 Schema

```sql
ALTER TABLE conversations ADD COLUMN summary_short TEXT;
ALTER TABLE conversations ADD COLUMN summary_full TEXT;
```

### 9.2 Resumo Curto (`generate_debate_summary()`)

- Max 5 linhas
- Topico, posicoes principais, consenso, aprendizado chave
- Prompt com ultimos 12 turnos

### 9.3 Resumo Completo (`generate_full_summary()`)

- Preserva contexto situacional
- Secoes: Contexto, Posicoes, Evolucao, Argumentos Decisivos, Consenso, Aprendizados, Proximos Passos
- Prompt com ultimos 24 turnos
- Fallback para resumo curto em caso de erro

### 9.4 Fluxo

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

## 10. Compactacao

### 10.1 Metodo `SessionFiles.compact_old_sessions()`

- Sessoes >30 dias
- Remove `transcript.json` (mantem `summary.json`)
- Comprime `metadata.json` (remove campos grandes, adiciona `compacted: true`)

### 10.2 Trigger

- Executado no startup (lifespan)
- Log de quantos transcripts foram compactados

### 10.3 Seguranca

- So deleta transcript se summary existe
- Verifica idade pela data no nome do diretorio
- Erros sao ignorados individualmente
