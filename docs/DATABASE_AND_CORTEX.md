# 🗄️ THZ Minds — Arquitetura de Persistência & Cortex DB

## 1. Banco SQLite Unificado (data/thz-room-cortex.db)
O sistema utiliza SQLite com modo **WAL (Write-Ahead Logging)** para máxima concorrência e integridade de dados.

---

## 2. Tabelas de Inteligência & Consenso
- conversations: Histórico de debates, IDs de sessão, status e total de turnos.
- messages: Registro completo de mensagens, turnos, votos e argumentos por agente.
- 	opic_memory: Tópicos discutidos e taxa de consenso histórico.
- gent_skills: Pontuação e evolução de expertise de cada agente por domínio técnico.
- debate_patterns: Padrões e catalisadores que levaram a consensos rápidos.
- rgument_embeddings: Vetores semânticos para RAG local.
- knowledge_graph: Grafo de relacionamentos conceituais entre tópicos discutidos.

---

## 3. Tabelas de TeamWork & Fábrica de Software
- 	eamwork_sessions: Registra id, project_name, mode, goal, output_dir, executive_summary e 	otal_steps.
- 	eamwork_artifacts: Registra o vínculo de cada arquivo gerado (ile_path, ile_type, uthor_role, content_length) com a sessão.
