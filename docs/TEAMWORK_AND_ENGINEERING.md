# ⚙️ THZ Minds — TeamWork & Fábrica Autônoma Multiagente

## 1. Visão Geral
O módulo **TeamWork** do THZ Minds transforma o conselho de agentes de um formato puramente conversacional para uma **linha de produção autônoma de software e conteúdo técnico de nível profissional**.

Os agentes trabalham em conjunto com papéis especializados, gerando código funcional, arquitetura, testes, Dockerfiles, documentação e artigos completos para o mundo real dentro do diretório output/.

---

## 2. Modos de Operação

### 2.1. Modo Engenharia de Software (TeamworkMode.ENGINEERING)
Simula um time de engenharia completo desenvolvendo um projeto do zero a partir de uma meta técnica ou cenário de produção.

#### Pipeline de Especialistas (7 Etapas Sequenciais):
1. **Product Specialist & Requirement Analyst**: Elabora especificação detalhada de requisitos funcionais e não-funcionais (docs/SPEC.md).
2. **Tech Lead & Principal Architect**: Define arquitetura de microsserviços/monolito, diagramas, contratos de API e modelo de dados (docs/ARCHITECTURE.md, docs/API_CONTRACT.md).
3. **Senior Backend Engineer**: Implementa código backend de produção, endpoints, validações e persistência segura (src/main.py, src/database.py).
4. **Senior Frontend & Integration Specialist**: Cria componentes, interfaces, schemas de validação e rotas de consumo (rontend/app.js, rontend/index.html).
5. **DevOps & Cloud Engineer**: Cria scripts de containerização, CI/CD, variáveis de ambiente e deploy (Dockerfile, docker-compose.yml, .env.example).
6. **QA Tester & Security Auditor**: Desenvolve suíte de testes unitários e de integração, e auditoria de vulnerabilidades (	ests/test_main.py, docs/SECURITY_AUDIT.md).
7. **Technical Documentation Engineer**: Redige o README.md final do projeto com instruções de execução, métricas e guia de contribuição.

---

### 2.2. Modo Fábrica de Artigos Técnicos (TeamworkMode.CONTENT)
Inspirado nas bancadas de revisão técnica de comunidades como DIO, dev.to e Medium, onde múltiplos especialistas colaboram e refinam um artigo técnico em alto nível.

#### Pipeline Editorial (6 Etapas Sequenciais):
1. **Technical Researcher**: Pesquisa referências, conceitos fundamentais e cases de produção (pauta.md).
2. **Lead Author**: Redige a primeira versão aprofundada com estrutura didática e exemplos (draft.md).
3. **Code Explainer & Developer**: Adiciona trechos de código executáveis, benchmarks e diagramas práticos (code_snippets.md).
4. **Fact Checker & Validator**: Valida a precisão técnica dos argumentos, compatibilidade de versões e boas práticas (act_check.md).
5. **Technical Reviewer**: Realiza a revisão crítica de clareza, tom de voz e profundidade técnica (
eview.md).
6. **Technical Editor**: Compila o artigo definitivo e pronto para publicação (ARTIGO_FINAL.md).

---

## 3. Gestão do Workspace & Estrutura de Arquivos
Todos os projetos gerados são salvos em output/<project_id>/ e contêm um manifesto com metadados estruturados:

`
output/
  project_eng_20260827_184844_d9e258/
    project_manifest.json
    README.md
    Dockerfile
    docker-compose.yml
    .env.example
    docs/
      SPEC.md
      ARCHITECTURE.md
      API_CONTRACT.md
      SECURITY_AUDIT.md
    src/
      main.py
      database.py
    tests/
      test_main.py
`

---

## 4. Endpoints da API
- POST /api/teamwork/start: Inicia a pipeline de forma síncrona retornando o JSON consolidado.
- POST /api/teamwork/stream: Streaming SSE em tempo real transmitindo o início e a conclusão de cada etapa.
- GET /api/teamwork/projects: Retorna o histórico de projetos salvos no CortexDB e no disco.
- GET /api/teamwork/file?project_id=...&file_path=...: Lê um arquivo gerado de forma segura.
- GET /api/scenarios/engineering: Retorna cenários de produção aleatórios.
- GET /api/scenarios/content: Retorna temas técnicos para pautas de artigos.
