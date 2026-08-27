# THZ Minds — Roadmap de Evolucao (12 Fases)

## Visao Geral

Este documento detalha as 12 fases de evolucao do sistema THZ Minds, cobrindo desde correcoes criticas de consenso ate funcionalidades avancadas como debate hibrido humano-IA.

**Data:** 2026-08-27
**Status:** Aprovado para implementacao
**Dependencias do documento:** `docs/ROADMAP.md` (implementacoes ja concluidas)

---

## Diagnostico Atual

### Metricas Reais (305 conversas, 1388 mensagens)

| Metrica | Valor | Problema |
|---------|-------|----------|
| Debates com consenso | 15/261 = **5.7%** | Barra de 9/9 agentes impossivel |
| Mensagens FORCE_STOP | 274 = **19.7%** | 3 detectores muito agressivos |
| Media de turnos por debate | **4.6** (de 48 max) | Debates morrem cedo |
| Conhecimento acumulado | **Inutil** | retrieve_knowledge busca so CONSENSUS (5.7%) |
| RAG embeddings | **0 indexados** | nomic-embed-text pode nao estar instalado |
| agent_skills | **Nunca lido** | Tabela existe mas nunca e injetada no prompt |
| Zero-trust | **Nenhum** | Todos os guardrails baseados em prompt |
| Interacao agentes | **Nenhuma** | Monologos sequenciais, sem perguntas |

### Ciclo Vicioso Identificado

```
Barra de consenso impossivel (9/9)
    ↓
Poucos debates com CONSENSUS (5.7%)
    ↓
Knowledge retrieval so busca CONSENSUS (quase nada)
    ↓
Agentes nao aprendem nada de debates anteriores
    ↓
Repeticao aumenta → FORCE_STOP mata debates cedo
    ↓
Ciclo vicioso
```

---

## FASE 1: Consenso + FORCE_STOP (Fundacao)

**Prioridade:** Critica | **Esforco:** Medio | **Depende de:** Nenhuma

### Problema
- Barra de consenso exige 9/9 agentes consecutivos (impossivel)
- 3 mecanismos de FORCE_STOP matam 19.7% das mensagens
- Debates tem media de 4.6 turnos

### Solucoes

#### 1A. Nova AgentDecision com question_to e reasoning

**Arquivo:** `server.py:90-96`

```python
class AgentDecision(BaseModel):
    argument: str
    status: Literal["CONTINUE", "CONSENSUS", "FORCE_STOP"]
    question_to: Optional[str] = Field(
        default=None,
        description="Nome do agente alvo (ex: 'SRE'), se tiver duvida sobre argumento dele."
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="Raciocinio interno (nao enviado ao debate)."
    )
```

#### 1B. Consenso por maioria qualificada (6/9)

**Arquivo:** `server.py:1308`

```python
# Antes:
if consecutive_consensus >= len(self.agents) and current_turn >= self.min_turns:

# Depois:
CONSENSUS_THRESHOLD = 6  # Maioria qualificada de 9 agentes
if consecutive_consensus >= CONSENSUS_THRESHOLD and current_turn >= self.min_turns:
```

#### 1C. Prompt de consenso mais flexivel

**Arquivo:** `server.py:1165`

```python
# Antes:
f"Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' apenas se houver concordancia total."

# Depois:
f"Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' quando concordar com a maioria dos pontos principais (nao precisa concordar com todos)."
```

#### 1D. Reduzir agressividade dos detectores

| Funcao | Mudanca |
|--------|---------|
| `_is_repetitive()` | 50→120 chars, min 5 args (nao 3), thresholds +0.05 |
| `_is_plagiarized()` | 8→12 word n-gram, overlap 0.9→0.95 |
| `LoopDetector` | REPETITION_LIMIT 5→8, PLAGIARISM_LIMIT 3→5, DIVERSITY_LOW 0.3→0.25 |

#### 1E. Consenso forçado nos ultimos turnos

**Arquivo:** `server.py` — adicionar antes do `break` (linha 1328):

```python
if current_turn >= self.max_turns - 3:
    instruction += "\nO debate esta terminando. Se concordar com a maioria, responda CONSENSUS."
```

#### 1F. Fix bug topic_exhausted

**Arquivo:** `server.py:1094`

```python
# Antes:
return

# Depois:
return False, "", ""
```

### Metricas Esperadas
- Consenso: 5.7% → ~30-40%
- FORCE_STOP: 19.7% → ~5%
- Media turnos: 4.6 → ~15

---

## FASE 2: RAG Funcional + Conhecimento Real

**Prioridade:** Alta | **Esforco:** Alto | **Depende de:** Fase 1

### Problema
- 2 sistemas de retrieval paralelos (SQL LIKE + embeddings)
- retrieve_knowledge() so busca mensagens CONSENSUS (5.7%)
- agent_skills existe mas nunca e lido
- debate_health table criada mas nunca populada

### Solucoes

#### 2A. Unificar retrieval — retrieve_knowledge() usa embeddings

**Arquivo:** `server.py:387-409`

```python
@staticmethod
async def retrieve_knowledge(topic: str, limit: int = 5) -> List[Dict]:
    # Tentar busca semantica primeiro
    semantic_results = await semantic_search.buscar_argumentos_similares(topic, limit=limit)
    if semantic_results:
        return semantic_results
    
    # Fallback: SQL LIKE (melhorado)
    topic_words = [w for w in topic.split() if len(w) > 3]
    # ... (manter fallback existente)
```

#### 2B. Auto-indexar embeddings a cada mensagem

**Arquivo:** `server.py` — apos `save_message()` (linha 1267):

```python
try:
    await self.semantic_search.indexar_argumentos_pendentes()
except Exception:
    pass  # Non-critical
```

#### 2C. Popular debate_health table

**Arquivo:** `server.py` — apos cada turno, salvar metricas:

```python
await CortexDB.save_debate_health(conversation_id, current_turn, health)
```

#### 2D. Injetar agent_skills no prompt

**Arquivo:** `server.py` — antes de montar `user_prompt`:

```python
agent_skills = await CortexDB.get_agent_skills()
if agent.name in agent_skills:
    skills_text = "\n".join(
        f"- {s['skill_domain']}: nivel {s['expertise_level']:.1f}"
        for s in agent_skills[agent.name]
    )
    knowledge_context += f"\n\n## Suas areas de expertise:\n{skills_text}\n"
```

#### 2E. Chamar update_agent_skills() no debate

**Arquivo:** `server.py` — apos `save_message()`:

```python
if effective_status == "CONSENSUS":
    await CortexDB.update_agent_skills(agent.name, topic, True)
```

#### 2F. Remover filtro CONSENSUS do retrieve_knowledge()

**Arquivo:** `server.py:406`

```python
# Antes:
AND m.status = 'CONSENSUS'

# Depois: remover esta linha (buscar todos os argumentos relevantes)
```

### Metricas Esperadas
- Knowledge retrieval: 0 → 100% funcional
- embeddings indexados: 0 → auto-indexacao
- agent_skills util: 0% → 100%

---

## FASE 3: Thinking/Reasoning + Chain-of-Thought

**Prioridade:** Alta | **Esforco:** Medio | **Depende de:** Fase 1

### Problema
- Agentes geram respostas sem raciocinio previo
- Sem mecanismo de pergunta/resposta entre agentes
- Sem follow-up em pontos especificos

### Solucoes

#### 3A. Prompt com reasoning step

**Arquivo:** `server.py` — system prompt dos agentes (linha 916):

```python
"RACIOCINIO: Antes de responder, analise:\n"
"1. O que o ultimo argumento realmente esta dizendo?\n"
"2. Ha dados concretos que suportam ou refutam?\n"
"3. Voce concorda com a maioria dos pontos?\n"
"4. Ha algo que nenhum agente mencionou ainda?\n"
"Preencha 'reasoning' com seu raciocinio interno.\n"
```

#### 3B. Mecanismo de pergunta/resposta

**Arquivo:** `server.py` — quando `decision.question_to` e definido:

```python
if decision.question_to:
    pending_question = {
        "from": agent.name,
        "to": decision.question_to,
        "question": decision.argument,
        "turn": current_turn
    }
```

Na iteracao do agente alvo:

```python
if pending_question and pending_question["to"] == agent.name:
    instruction += f"\nPERGUNTA DE {pending_question['from']}: {pending_question['question']}\n"
    instruction += "Responda diretamente a essa pergunta. Se satisfatoria, considere CONSENSUS.\n"
```

#### 3C. Prompt para perguntas

```python
"- Se voce tiver DUVIDA sobre um argumento de outro agente, use 'question_to' com o nome do agente.\n"
"- Formato: PERGUNTA PARA [Nome]: [sua duvida]\n"
"- Responda CONSENSUS se a pergunta for respondida satisfatoriamente.\n"
```

### Metricas Esperadas
- Interacao real entre agentes: 0% → ~60% dos debates
- Qualidade de argumentos: melhoria com reasoning

---

## FASE 4: Validacao de Argumentos + Scoring

**Prioridade:** Media | **Esforco:** Medio | **Depende de:** Fase 2

### Problema
- Quality scores computados e descartados
- Nenhum argumento rejeitado por baixa qualidade
- debate_health table nunca populada

### Solucoes

#### 4A. Expandir AgentDecision com confidence

**Arquivo:** `server.py`

```python
class AgentDecision(BaseModel):
    argument: str
    status: Literal["CONTINUE", "CONSENSUS", "FORCE_STOP"]
    question_to: Optional[str] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
```

#### 4B. Nova tabela argument_scores

**Arquivo:** `server.py` — migration:

```sql
CREATE TABLE IF NOT EXISTS argument_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT,
    agent_name TEXT,
    quality_score REAL,
    novelty_score REAL,
    expertise_alignment REAL,
    confidence REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 4C. Persistir scores no DB

```python
await CortexDB.save_argument_score(message_id, agent.name, quality, novelty, expertise, confidence)
```

#### 4D. Usar scores para influenciar consenso

```python
# Se argumento tem quality_score < 0.3, nao contar para consenso
# Se confidence > 0.8 e status=CONSENSUS, peso maior
```

#### 4E. Rejeitar argumentos de baixa qualidade

```python
if quality.get("overall_score", 1.0) < 0.2 and current_turn > self.min_turns:
    effective_status = "CONTINUE"  # Forcar continue para retry
```

---

## FASE 5: Humano no Loop + Zero-Trust

**Prioridade:** Critica | **Esforco:** Alto | **Depende de:** Fase 1

### Problema
- Nenhum mecanismo de validacao humana
- Todos os guardrails baseados em prompt
- Botao de parar na GUI nao funciona

### Arquitetura de Seguranca

```python
class ActionType(Enum):
    READ_ONLY = "read_only"      # Gerar texto, ler DB — permitido
    WRITE_DB = "write_db"        # Salvar mensagem — permitido
    CONSENSUS = "consensus"      # Marcar consenso — requer validacao
    DELEGATE = "delegate"         # Delegar tarefa — requer validacao
    DANGEROUS = "dangerous"      # Deletar, modificar config — BLOQUEADO sem humano
```

### Solucoes

#### 5A. Evento de validacao humana

**Arquivo:** `server.py`

```python
await websocket.send_json({
    "event": "human_validation_required",
    "data": {
        "type": "consensus_reached",
        "topic": topic,
        "summary": summary_short,
        "requires_approval": True
    }
})
# Aguardar resposta do humano (timeout 60s)
response = await asyncio.wait_for(websocket.receive_json(), timeout=60.0)
```

#### 5B. Gate de validacao

```python
async def requires_human_approval(action: ActionType, context: dict) -> bool:
    if action == ActionType.DANGEROUS:
        return True
    if action == ActionType.CONSENSUS:
        return context.get("times_discussed", 0) > 3
    return False
```

#### 5C. Interface GUI para aprovacao

**Arquivo:** `gui.py` — novos botoes:
- "Aprovar Consenso" — finaliza debate
- "Rejeitar / Continuar Debate" — força CONTINUE
- "Encerrar Debate" — FORCE_STOP

#### 5D. Fix botao de parar

**Arquivo:** `gui.py` — o botao de parar deve enviar sinal real ao server via WebSocket.

---

## FASE 6: Agrupamento de Conhecimento

**Prioridade:** Media | **Esforco:** Alto | **Depende de:** Fase 2

### Problema
- Nenhum mecanismo de clustering de topicos
- Sem knowledge graph
- Sem agrupamento de conceitos relacionados

### Solucoes

#### 6A. Topic clustering via embeddings

**Arquivo:** `rag/semantic_search.py`

```python
async def cluster_topics(self, n_clusters: int = 10) -> Dict[str, List[str]]:
    """Agrupa topicos similares usando embeddings."""
    # Buscar todos os embeddings
    # Aplicar clustering (K-means ou DBSCAN simplificado)
    # Retornar mapeamento cluster → topicos
```

#### 6B. Knowledge graph — nova tabela

```sql
CREATE TABLE IF NOT EXISTS knowledge_graph (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_topic TEXT,
    target_topic TEXT,
    relationship TEXT,  -- "similar", "contradicts", "builds_on", "subset_of"
    strength REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### 6C. Injetar contexto de cluster no prompt

```python
if cluster:
    knowledge_context += f"\nEste topico faz parte do cluster '{cluster_name}' junto com: {related_topics}\n"
```

---

## FASE 7: Tool Use / Function Calling

**Prioridade:** Alta | **Esforco:** Alto | **Depende de:** Fase 1

### Problema
- Agentes so geram texto
- Nao podem buscar dados reais na web
- Nao podem executar codigo ou consultar APIs

### Solucoes

#### 7A. Schema de tool calls

**Arquivo:** `server.py`

```python
class ToolCall(BaseModel):
    tool: str  # "web_search", "code_execute", "api_call", "db_query"
    params: Dict[str, str]
    
class AgentDecision(BaseModel):
    # ... (campos anteriores)
    tool_call: Optional[ToolCall] = None
```

#### 7B. Ferramentas disponiveis

**Novo arquivo:** `tools/registry.py`

```python
TOOLS = {
    "web_search": WebSearchTool(),      # Busca web via DuckDuckGo
    "code_execute": CodeExecuteTool(),  # Executa Python sandboxed
    "db_query": DBQueryTool(),          # Consulta o DB de debates
    "file_read": FileReadTool(),        # Le arquivos do projeto
}
```

#### 7C. Loop de tool calls

```python
if decision.tool_call:
    tool_result = await execute_tool(decision.tool_call)
    instruction += f"\nResultado da ferramenta '{decision.tool_call.tool}':\n{tool_result}\n"
```

#### 7D. Zero-Trust para tools

```python
TOOL_PERMISSIONS = {
    "web_search": ActionType.READ_ONLY,
    "db_query": ActionType.READ_ONLY,
    "file_read": ActionType.READ_ONLY,
    "code_execute": ActionType.DANGEROUS,
}
```

---

## FASE 8: Voto Ponderado por Expertise

**Prioridade:** Alta | **Esforco:** Medio | **Depende de:** Fase 2

### Problema
- Todos os agentes tem mesmo peso
- Agente com expertise nao tem mais influencia

### Solucoes

#### 8A. Calcular peso de voto

```python
async def calculate_vote_weight(agent_name: str, topic: str) -> float:
    skills = await CortexDB.get_agent_skills()
    if agent_name in skills:
        expertise = sum(s['expertise_level'] for s in skills[agent_name])
        return min(1.0, 0.5 + (expertise * 0.1))
    return 0.5
```

#### 8B. Consenso ponderado

```python
weighted_score = sum(
    await calculate_vote_weight(a.name, topic)
    for a in self.agents
    if a.name in consensus_voters
) / sum(
    await calculate_vote_weight(a.name, topic)
    for a in self.agents
)

if weighted_score >= 0.7 and current_turn >= self.min_turns:
    # Consenso atingido
```

#### 8C. Injetar peso no prompt

```python
f"Seu peso de voto atual: {vote_weight:.1f} (baseado na sua expertise).\n"
```

---

## FASE 9: Debate Persistente / Retomavel

**Prioridade:** Media | **Esforco:** Medio | **Depende de:** Fase 1

### Problema
- Debates nao podem ser pausados e retomados
- Estado do debate so existe na memoria

### Solucoes

#### 9A. Tabela de estado do debate

```sql
CREATE TABLE IF NOT EXISTS debate_state (
    conversation_id TEXT PRIMARY KEY,
    topic TEXT,
    current_turn INTEGER,
    history_json TEXT,
    status TEXT,  -- "active", "paused", "completed"
    session_id TEXT,
    created_at DATETIME,
    updated_at DATETIME
);
```

#### 9B. Salvar estado automaticamente

```python
if current_turn % 5 == 0:
    await CortexDB.save_debate_state(conversation_id, history, current_turn, "active")
```

#### 9C. Endpoint para pausar

```python
@app.websocket("/ws/debate/{conversation_id}/pause")
async def pause_debate(websocket: WebSocket, conversation_id: str):
    await CortexDB.save_debate_state(conversation_id, history, current_turn, "paused")
```

#### 9D. Endpoint para retomar

```python
@app.post("/api/debate/{conversation_id}/resume")
async def resume_debate(conversation_id: str):
    state = await CortexDB.get_debate_state(conversation_id)
    # Restaurar e continuar
```

---

## FASE 10: Dashboard de Reputacao + Exportacao

**Prioridade:** Media | **Esforco:** Alto | **Depende de:** Fase 4

### Solucoes

#### 10A. Dashboard de reputacao

**Arquivo:** `server.py` — novos endpoints:

```python
@app.get("/api/agents/reputation")
async def get_agent_reputation():
    skills = await CortexDB.get_agent_skills()
    contributions = await CortexDB.get_agent_contributions()
    return {"skills": skills, "contributions": contributions}
```

**Arquivo:** `gui.py` — nova aba "Reputacao":
- Grafico de barras com expertise_level por agente
- Timeline de contribuicoes para consenso
- Ranking de agentes

#### 10B. Exportacao de relatorios

**Novo arquivo:** `export/report_generator.py`

```python
class ReportGenerator:
    def generate_markdown(self, conversation_id: str) -> str:
        # Topico, data, participantes
        # Resumo executivo
        # Turnos do debate
        # Consenso/score
        # Estatisticas
        
    def generate_pdf(self, conversation_id: str) -> bytes:
        # Usar weasyprint ou reportlab
        pass
```

**Arquivo:** `gui.py` — botao "Exportar Relatorio":
- Selecionar formato (Markdown/PDF)
- Download do arquivo

---

## FASE 11: Multi-Modelo por Agente

**Prioridade:** Media | **Esforco:** Medio | **Depende de:** Fase 1

### Solucoes

#### 11A. Configuracao de modelo por agente

**Arquivo:** `server.py` — modificar `create_agents()`:

```python
DEFAULT_AGENT_MODELS = {
    "Arquiteto": "qwen2.5:7b",
    "SRE": "qwen2.5:7b",
    "DevOps": "qwen2.5:7b",
    "DBA": "qwen2.5:7b",
    "Security": "qwen2.5:7b",
    "PO": "llama3.1:8b",
    "Scrum Master": "llama3.1:8b",
    "Gerente": "llama3.1:8b",
    "Dev Senior": "qwen2.5:7b",
}
```

#### 11B. Endpoint para listar modelos

```python
@app.get("/api/models")
async def list_models():
    # Retorna modelos disponiveis no Ollama
    pass
```

#### 11C. Interface GUI

- Dropdown por agente na tela de configuracao
- Salvar configuracao em `config.json`

---

## FASE 12: Debate Hibrido Humano-IA

**Prioridade:** Alta | **Esforco:** Alto | **Depende de:** Fase 5

### Solucoes

#### 12A. Modo de debate

```python
class DebateMode(Enum):
    AGENT_ONLY = "agent_only"
    HUMAN_INITIATED = "human_initiated"
    HUMAN_MODERATED = "human_moderated"
    COLLABORATIVE = "collaborative"
```

#### 12B. WebSocket para participacao humana

```python
@app.websocket("/ws/debate/{conversation_id}/human")
async def human_participation(websocket: WebSocket, conversation_id: str):
    # Humano entra no debate
    # Envia argumentos via WebSocket
    # Recebe turnos dos agentes em tempo real
```

#### 12C. Interface GUI

- Botao "Participar do Debate"
- Input de texto para enviar argumento
- Indicador de turno (humano ou agente)
- Timeout configuravel para resposta do humano

---

## FASE Futura: Neural/Deep Learning (Adiado)

> Componentes que usam Torch e derivados — implementar quando fases 1-12 estiverem estaveis.

| Componente | Descricao | Dependencias |
|------------|-----------|-------------|
| Argument Scoring NN | Rede neural para avaliar qualidade | torch, sklearn |
| Topic Clustering | DBSCAN/K-means nos embeddings | torch, numpy |
| Consensus Predictor | MLP para prever consenso | torch |
| Sentiment Analysis | Analise de sentimento | transformers |
| Fine-tuning | QLoRA nos agentes com dados reais | unsloth, trl, peft |

---

## Ordem de Implementacao

```
Fase 1 (Consenso) → Fase 2 (RAG) → Fase 3 (Reasoning)
    ↓                                    ↓
Fase 5 (Zero-Trust) ←────────────── Fase 4 (Scoring)
    ↓
Fase 7 (Tool Use) → Fase 8 (Voto Ponderado)
    ↓
Fase 9 (Persistente) → Fase 10 (Dashboard + Export)
    ↓
Fase 11 (Multi-Modelo) → Fase 12 (Hibrido)
    ↓
Futuro: Neural/Deep Learning
```

---

## Arquivos Afetados por Fase

| Fase | Arquivos Principais |
|------|---------------------|
| 1 | `server.py`, `stability/loop_detector.py` |
| 2 | `server.py`, `rag/semantic_search.py` |
| 3 | `server.py` (prompts) |
| 4 | `server.py`, nova tabela `argument_scores` |
| 5 | `server.py`, `gui.py` |
| 6 | `rag/semantic_search.py`, nova tabela `knowledge_graph` |
| 7 | Novo: `tools/registry.py`, `server.py` |
| 8 | `server.py` |
| 9 | `server.py`, nova tabela `debate_state` |
| 10 | `gui.py`, Novo: `export/report_generator.py` |
| 11 | `server.py`, `gui.py` |
| 12 | `server.py`, `gui.py` |

---

## Metricas de Sucesso

| Metrica | Antes | Target |
|---------|-------|--------|
| Taxa de consenso | 5.7% | 30-40% |
| FORCE_STOP | 19.7% | ~5% |
| Media turnos/debate | 4.6 | ~15 |
| Knowledge retrieval funcional | 0% | 100% |
| embeddings indexados | 0 | auto |
| agent_skills util | 0% | 100% |
| Zero-trust enforcement | 0 | 100% |
| Interacao humana | Nenhuma | Hibrida |
