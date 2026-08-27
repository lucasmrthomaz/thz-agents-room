# 🔌 THZ Minds — Protocolo OpenAI-Compatible (v1)

## 1. Visão Geral
Para permitir a integração direta com a **Thz-Lang** e ferramentas do mercado (Cursor IDE, Continue.dev, Dify, LangChain, LlamaIndex), o THZ Minds implementa uma camada de compatibilidade com a API da OpenAI (/v1).

---

## 2. Endpoints Disponíveis

### 2.1. Listagem de Modelos (GET /v1/models)
Retorna os modelos e especialistas disponíveis:
- 	hz-council-auto: Conselho completo com deliberação de especialistas.
- 	hz-engineering-team: Time de engenharia autônomo.
- 	hz-content-team: Linha de revisão técnica e artigos.

---

### 2.2. Chat Completions (POST /v1/chat/completions)
Recebe payloads compatíveis com a especificação OpenAI:
- Validação semântica de escopo com ScopeGuard.
- Suporte a respostas em JSON ou streaming Server-Sent Events (stream: true).
