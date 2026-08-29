# MALE - Motor Multiagente Local

## O que e

Sistema que roda 9 LLMs locais (Ollama) debatendo autonomamente sobre temas de tecnologia.
Tudo e salvo em SQLite. Turnos dinamicos. Documentacao para futura revisao.

## Temas Permitidos (Guardrails)

Os agentes SO podem discutir sobre:

- Programacao - linguagens, padroes, frameworks, boas praticas
- Arquitetura de Software - monolito vs microservicos, design de sistemas
- Git e Controle de Versao - branching, merge, CI
- Sistemas Operacionais - Linux, Windows, processos, memoria, I/O
- Lideranca Tecnica - gestao, mentoria, tomada de decisao
- Problemas Humano-Computador - UX, produtividade, automacao
- DevOps e Infraestrutura - containers, cloud, monitoramento
- Banco de Dados - SQL, NoSQL, modelagem, performance
- Seguranca - vulnerabilidades, autenticacao, boas praticas

**Fora do escopo:** politica, opinioes pessoais, conteudo nao-tecnico.

O orquestrador rejeita topicos que fogem desses guardrails.

## Agentes (9 total)

### Tecnicos (6)

| Nome | Papel | Pessoa / Especialidade |
|------|-------|------------------------|
| Arquiteto | KISS, simplicidade, custo de infraestrutura | Carlos Magno - 20 anos arquitetura |
| SRE | Tolerancia a falhas, resiliencia, SPOF | Fernanda Ribeiro - ex-Google SRE |
| DevOps | CI/CD, infraestrutura como codigo, automacao | Andre Santos - 8 anos DevOps |
| DBA | Modelagem de dados, performance de queries | Patricia Lima - ex-Oracle DBA |
| Security | Vulnerabilidades, autenticacao, boas praticas | Marcos Oliveira - 12 anos seguranca |
| Desenvolvedor | 8 anos fullstack, React/Node/Python | Lucas Mendes - criterios praticos |

### Negocio (3)

| Nome | Papel | Pessoa / Especialidade |
|------|-------|------------------------|
| PO | Valor de negocio, ROI, priorizacao | Marina Costa - PO senior |
| Scrum Master | Processo, impedimentos, fluxo de trabalho | Rafael Santos - 6 anos SM |
| Gerente | Prazo, recursos, riscos, orcamento | Ana Beatriz - gerente de projetos |

## Dinamica de Turnos

### Antes (Rodizio Simples)
- 18 turnos fixos, ordem pre-definida
- Todos 9 com CONSENSUS -> encerra

### Agora (Turnos Dinamicos por Leilao)

1. **SpeakerSelector** calcula pontuacao para cada agente:
   - Relevancia da expertise (+5)
   - Recencia (-3 se falou recentemente)
   - Turnos desde ultima fala (+2)
   - Questoes pendentes (+10)
   - Penalidade se bloqueado (-100)

2. **Top 3 candidatos** sao sorteados (maior pontuacao = maior chance)

3. **Nao-rodizio**: agentes podem ficar calados por turnos

4. **Questoes**: qualquer agente pode perguntar para outro (bônus +10)

## Consenso por Voting

- **Maioria simples**: 5 de 9 votos "agree" = consenso
- Cada agente emite voto: `agree`, `disagree` ou `abstain`
- **MetaModerator** decide quando forcar voting (baseado em progresso)
- Nao precisa mais de 9 concordancias consecutivas

## Anti-Ciclos e Anti-Conformidade

- **LoopDetector** mede diversidade semanal (bi-gramas)
- Se < 40% diversidade: injeta instrucao para discordar
- **Anti-conformidade forçada**: se muitos concordam, forca discordancia
- **Redirecionamento**: se repeticao detectada, pede perspectiva nova

## Meta-Moderacao

O MetaModerator monitora:
- Tendencia de consenso (muitos votos "agree")
- Nivel de conflito (muitos "disagree")
- Progresso do debate (argumentos evoluiram?)
- Perguntas sem resposta
- Consenso apressado

Acoes:
- `continue` - debate normal
- `force_vote` - pedir voting
- `finalize` - sintetizar e encerrar

## Identidade dos Agentes

Cada agente tem **SOUL.md** (Persistente entre debates):
- Biografia detalhada (experiencia real)
- Estilo de fala (tecnico, pratico, visionario, etc.)
- Estilo de discordancia (duvidador, provador, oposicionista)
- Exemplos de fala (few-shot)
- Memoria de episodios anteriores (acertos, erros, topics)

## Anonimizacao

- Transcritos sao **anonimizados** nos prompts dos agentes
- Remove: "Arquiteto", "SRE", "DevOps", etc.
- Usa: "Participante A", "Participante B", etc.
- Baseado em ACL 2026: reduz vies de autoridade

## Configuracao

| Parametro | Default | Minimo | Maximo |
|-----------|---------|--------|--------|
| max_turns | 25 | 6 | 50 |
| min_turns | 8 | 3 | 15 |
| num_ctx | 8192 | 4096 | 32768 |
| duration_hours | 8.0 | 0.5 | 24.0 |
| pause_between | 10min | - | - |
| model | qwen2.5:7b | - | - |
| consensus_threshold | 5 | 3 | 9 |

## Arquivos

| Arquivo | Descricao |
|---------|-----------|
| server.py | Servidor FastAPI + WebSocket + FSM + Ollama |
| agents/soul.py | Identidade persistente (SOUL.md + metadados) |
| agents/memory.py | Memoria episodica + semantica por agente |
| stability/conversation_summarizer.py | Resumo LLM a cada 3 turnos |
| stability/meta_moderator.py | Moderacao proativa + sintese final |
| stability/speaker_selector.py | Turnos dinamicos por leilao |
| stability/loop_detector.py | Deteccao de ciclos + anti-conformidade |
| stability/quality_monitor.py | DAR + bigramas + dados concretos |
| client.py | Cliente CLI (single + autonomous) |
| data/thz-room-cortex.db | Banco de inteligencia interna |
| sessions/ | Sessoes salvas por data |

## Pesquisa Utilizada

- **DAR** (arxiv 2603.20640) - Deteccao de argumentos repetidos
- **FREE-MAD** (ACL 2026) - Decoanoniomizacao
- **Meta-Moderator** (arxiv 2608.23029) - Moderacao meta-cognitiva
- **PGMem** (arxiv 2608.01708) - Memoria persistente
- **Anti-sycophancy** (SIGDIAL 2026) - Reducao de vies
- **Summary-based** (arxiv 2607.27942) - Comunicacao por resumo


-----------------------


# Local Multi-Agent Stack — RTX 4060 8GB

## Hardware

- GPU: RTX 4060 8GB
- RAM: 48GB DDR4 3200MHz
- Embeddings: nomic-embed-text

---

## Agent Architecture

### 🧠 Supervisor / Architect

**Model:** `gemma4:26b-a4b-it-qat`

**Role:**
- Planejamento complexo
- Decomposição de problemas
- Decisões arquiteturais
- Revisão de resultados
- Debugging complexo
- Supervisão dos demais agentes

**Execution:**
- GPU + RAM
- Não cabe integralmente nos 8GB VRAM
- Usar apenas quando a tarefa justificar o custo

---

### ⚙️ Primary Worker

**Model:** `gemma4:12b-it-qat`

**Role:**
- Modelo padrão dos agentes
- Coding
- Tool Calling
- Análise de arquivos
- APIs
- Transformação de dados
- Execução de tarefas
- Raciocínio intermediário

**Execution:**
- GPU-first
- ~7.2GB
- Melhor equilíbrio entre qualidade, VRAM e latência

---

### ⚡ Fast Worker

**Model:** `qwen3.5:9b`

**Role:**
- Classificação
- Extração
- JSON estruturado
- Resumos
- Roteamento
- Tarefas simples
- Tool selection
- Workers de baixa latência

**Execution:**
- GPU-first
- ~6.6GB
- Prioridade: velocidade

---

### 🔎 RAG / Embeddings

**Model:** `nomic-embed-text:latest`

**Role:**
- Embeddings
- Busca semântica
- RAG
- Indexação de documentos

**Execution:**
- Modelo auxiliar
- Não participa diretamente do raciocínio

---

# Routing Strategy

```text
                     USER
                       │
                       ▼
                ┌─────────────┐
                │   ROUTER    │
                └──────┬──────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      SIMPLE        NORMAL       COMPLEX
          │            │            │
          ▼            ▼            ▼
     Qwen 9B       Gemma 12B    Gemma 26B
     FAST WORKER   PRIMARY       SUPERVISOR
                   WORKER

