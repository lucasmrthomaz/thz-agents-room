# MALE - Motor Multiagente Local

## O que e

Sistema que roda 8 LLMs locais (Ollama) debatendo entre si sobre temas de tecnologia.
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

## Agentes (8 total)

### Tecnicos (5)

| Nome | Papel |
|------|-------|
| Arquiteto | KISS, simplicidade, custo de infraestrutura |
| SRE | Tolerancia a falhas, resiliencia, SPOF |
| DevOps | CI/CD, infraestrutura como codigo, automacao |
| DBA | Modelagem de dados, performance de queries, normalizacao |
| Security | Vulnerabilidades, autenticacao, boas praticas de seguranca |
| Desenvolvedor Senior |
| Desenvolvedor Pleno |
| Desenvolvedor Junior |
| QA Tester | 

### Negocio (3)

| Nome | Papel |
|------|-------|
| PO | Valor de negocio, ROI, priorizacao |
| Scrum Master | Processo, impedimentos, fluxo de trabalho |
| Gerente | Prazo, recursos, riscos, orcamento |

## Dinamica de Turnos

- Total: 18 turnos (2 rodadas completas de 8 agentes + 2 turnos extras)
- Ordem: Arquiteto -> SRE -> DevOps -> DBA -> Security -> PO -> Scrum Master -> Gerente -> repete
- Consenso: todos 8 com CONSENSUS -> encerra
- Timeout: 18 turnos atingidos
- Guard: turnos < 3 forca CONTINUE (anti-colapso prematuro)

## Selecao de Modelo

Prioridade de resolucao:

1. Modelo definido pelo usuario via payload do cliente
2. Variavel de ambiente OLLAMA_MODEL
3. Auto-discovery: maior modelo disponivel no Ollama
4. Fallback: qwen2.5:7b

## Modos de Operacao

### Single (Sob Demanda)
- Usuario envia um topico
- Roda 18 turnos
- Encerra

### Autonomous (Sessao Noturna)
- Roda debates por X horas (default: 8h)
- Ollama gera topicos automaticamente
- Pausa de 10 minutos entre debates
- Ao final: resumo matinal gerado por LLM
- Sessoes salvas em `sessions/`

## Configuracao

| Parametro | Default | Minimo | Maximo |
|-----------|---------|--------|--------|
| max_turns | 18 | 6 | 50 |
| num_ctx | 8192 | 4096 | 32768 |
| duration_hours | 8.0 | 0.5 | 24.0 |
| pause_between | 10min | - | - |
| model | auto | - | - |

## Eventos WebSocket

| Evento | Direcao | Payload |
|--------|---------|---------|
| init | Client->Server | {topic, max_turns, num_ctx, model?} |
| session_start | Server->Client | {session_id, duration_hours, model} |
| debate_start | Server->Client | {debate_num, topic} |
| turn_start | Server->Client | {turn, agent, role} |
| turn_end | Server->Client | {turn, agent, argument, status} |
| debate_complete | Server->Client | {debate_num, reason, total_turns} |
| session_complete | Server->Client | {total_debates, topics, summary} |
| error | Server->Client | {message} |

## Persistencia

### thz-room-cortex.db (Inteligencia Interna)
Banco unico com WAL mode. Tabelas:

- conversations - debates realizados
- messages - mensagens por turno
- topic_memory - topicos ja discutidos e resultados
- agent_skills - expertise de cada agente por dominio
- debate_patterns - padroes de consenso aprendidos
- content_references - referencias a boas praticas

### sessions/ (Sessoes Salvas)
```
sessions/
  2026-08-26/
    22-00/
      session_id/
        metadata.json
        debate_001/
          metadata.json
          transcript.json
          summary.json
        nightly_summary.json
```

## Arquivos

| Arquivo | Descricao |
|---------|-----------|
| server.py | Servidor FastAPI + WebSocket + FSM + Ollama |
| client.py | Cliente CLI (single + autonomous) |
| data/thz-room-cortex.db | Banco de inteligencia interna |
| sessions/ | Sessoes salvas por data |
