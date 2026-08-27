# THZ Minds — Motor Multiagente Local
(ORIGINALMENTE thz-agents-room)

**8 LLMs (agora 9) debatendo sobre tecnologia em tempo real via Ollama.**

Sistema local de debates multiagente onde agentes de IA discutem temas de tecnologia, Constroem conhecimento ao longo do tempo e geram resumos automaticos.

(Atualmente em longo processo de refinamento)
<img width="100%" height="100%" alt="image" src="https://github.com/user-attachments/assets/0b6b3cbe-4cec-42c2-9072-2a92efdcd4ed" />

```
  THZ Minds — Motor Multiagente Local
  9 LLMs debatendo sobre tecnologia
```

---

## Features

- **9 Agentes Especializados** — 6 tecnicos + 3 de negocio, cada um com sua expertise
- **Debates em Tempo Real** — WebSocket + GUI Tkinter com cores por agente
- **Modo Autonomo** — Sessoes noturnas com topics gerados automaticamente
- **Deteccao de Plagio** — N-gramas + frases inteiras, força originalidade
- **Anti-Loop** — Diversity score + trend analysis, encerra espirais
- **Base de Conhecimento** — Debates anteriores alimentam novas discussões
- **Resumo Automatico** — Resumo curto + completo ao final de cada debate
- **Idempotencia** — Chaves unicas em mensagens, upserts atomicos, request dedup
- **Compactacao** — Sessoes antigas comprimidas automaticamente (>30 dias)
- **RAG + Embeddings** — Busca semantica de argumentos relevantes (opcional)
- **Fine-tuning QLoRA** — Pipeline completo para treinar modelos por agente

---

## Agentes

| # | Agente | Foco |
|---|--------|------|
| 1 | **Arquiteto** | KISS, YAGNI, simplicidade, custo de infraestrutura |
| 2 | **SRE** | Tolerancia a falhas, SPOF, escalabilidade, observabilidade |
| 3 | **DevOps** | CI/CD, IaC, containers, automacao |
| 4 | **DBA** | Modelagem relacional, queries, indexes, NoSQL vs SQL |
| 5 | **Security** | Vulnerabilidades, autenticacao, injecao, exposicao |
| 6 | **Dev Senior** | SOLID, clean code, testes, code smells |
| 7 | **PO** | Valor de negocio, ROI, priorizacao |
| 8 | **Scrum Master** | Processo, impedimentos, fluxo de trabalho |
| 9 | **Gerente** | Prazo, recursos, riscos, orcamento |

---

## Requisitos

- Python 3.10+
- [Ollama](https://ollama.ai) instalado e rodando
- Modelo: `qwen2.5:7b` (padrao)
- Opcional: `nomic-embed-text` para RAG com embeddings

```bash
# Instalar Ollama e modelo
ollama pull qwen2.5:7b
ollama pull nomic-embed-text  # opcional, para RAG
```

---

## Instalacao

```bash
# Clonar repositorio
git clone https://github.com/seu-usuario/thz-agents-room.git
cd thz-agents-room

# Instalar dependencias
pip install -r requirements.txt

# Iniciar (GUI)
.\run.ps1          # Windows
./run.sh           # Linux/Mac

# Ou iniciar direto
python main.py     # GUI
python client.py   # CLI
```

---

## Uso

### GUI Grafica

```bash
python main.py
```

- Selecione **Single** (debate sob demanda) ou **Autonomo** (sessao noturna)
- Digite o topico ou deixe o sistema gerar
- Clique **Iniciar** — os agentes debatam em tempo real
- Ao final, resumo automatico e exibido

### Terminal (CLI)

```bash
# Debate unico
python client.py --mode single --topic "Docker vs Kubernetes"

# Modo autonomo (8 horas)
python client.py --mode autonomous --hours 8

# Com modelo especifico
python client.py --mode single --topic "Microservicos" --model qwen2.5:7b
```

### APIs

```bash
# Iniciar servidor
python server.py

# WebSocket
ws://127.0.0.1:8000/ws/debate

# Payload single
{"mode": "single", "topic": "APIs REST vs gRPC", "max_turns": 48}

# Payload autonomo
{"mode": "autonomous", "duration_hours": 8, "max_turns": 48}
```

---

## Arquitetura

```
┌──────────────┐     WebSocket     ┌──────────────┐
│  GUI Tkinter │ ◄──────────────► │  FastAPI WS   │
│  (gui.py)    │                   │  (server.py)  │
└──────────────┘                   └──────┬───────┘
                                          │
                                   ┌──────▼───────┐
                                   │   Ollama     │
                                   │  (qwen2.5)   │
                                   └──────┬───────┘
                                          │
                                   ┌──────▼───────┐
                                   │  SQLite DB    │
                                   │  (cortex)     │
                                   └──────────────┘
```

### Modulos

| Modulo | Descricao |
|--------|-----------|
| `server.py` | Motor principal — agentes, FSM, Ollama, WebSocket |
| `client.py` | Cliente CLI para debater via terminal |
| `gui.py` | Interface Tkinter com cores, loading, sidebar |
| `main.py` | Entry point para GUI |
| `rag/` | Embeddings, vector store, busca semantica |
| `stability/` | Context manager, loop detector, quality monitor |
| `training/` | Fine-tuning QLoRA, export dataset, deploy |

---

## Banco de Dados

Tabelas SQLite (`data/thz-room-cortex.db`):

| Tabela | Descricao |
|--------|-----------|
| `conversations` | Debates + summary_short + summary_full |
| `messages` | Argumentos com idempotency_key |
| `topic_memory` | Topicos discutidos com upsert atomico |
| `agent_skills` | Expertise por agente com upsert atomico |
| `argument_embeddings` | Embeddings para busca semantica |

---

## Performance

| Metrica | Valor |
|---------|-------|
| Turnos por debate | 48 (configuravel 6-50) |
| Pausa entre debates | 1 minuto (modo autonomo) |
| Deteccao de plagio | N-gramas de 8 palavras + frases 90% |
| Validacao de idioma | Rejeita texto nao-portugues |
| Context window | Auto-expand 8192 → 32768 |
| Idempotencia | Chaves unicas + upserts atomicos |
| Compactacao | Sessoes >30 dias automaticas |

---

## Fine-tuning (Opcional)

Pipeline completo para treinar modelos locais por agente:

```bash
# 1. Exportar dataset
python training/export_dataset.py

# 2. Filtrar qualidade
python training/quality_filter.py

# 3. Treinar QLoRA (requer GPU)
python training/train_qlora.py

# 4. Deploy para Ollama
python training/deploy_to_ollama.py
```

**Hardware minimo:** RTX 4060 8GB (QLoRA 7B)

---

## Roadmap

Ver [docs/ROADMAP.md](docs/ROADMAP.md) para detalhes completos.

- [x] 9 agentes especializados
- [x] Deteccao de plagio e repeticao
- [x] Resumo automatico de debates (curto + completo)
- [x] Base de conhecimento
- [x] GUI com sidebar e loading
- [x] Modo autonomo
- [x] RAG + embeddings (opcional)
- [x] Fine-tuning QLoRA pipeline
- [x] Idempotencia no banco e aplicacao
- [x] Compactacao de sessoes antigas
- [ ] Dashboard web (futuro)
- [ ] Multi-modelo por agente (futuro)

---

## Testes

```bash
# Rodar todos os testes
python -m pytest tests/ -v

# Com cobertura
python -m pytest tests/ -v --cov=.
```

58 testes unitarios e de integracao.

---

## Licenca

GPL V3

---

**Desenvolvido com Python + Ollama + FastAPI + Tkinter**
