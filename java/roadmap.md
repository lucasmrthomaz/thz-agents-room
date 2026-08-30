# MALE Java - Roadmap de Implementacao

## Decisoes de Arquitetura

| Decisao | Escolha |
|---------|---------|
| Framework | Spring Boot 4.x |
| AI | Spring AI 2.x (`spring-ai-starter-model-ollama`) |
| UI | Thymeleaf + WebSocket STOMP |
| DB | SQLite (compativel com `thz-room-cortex.db` do Python) |
| Build | Maven |
| Java | 21+ |

## Stack completa

```xml
spring-boot-starter-webmvc
spring-boot-starter-thymeleaf
spring-boot-starter-websocket
spring-boot-starter-data-jpa
spring-ai-starter-model-ollama
sqlite-jdbc + org.xerial:sqlite-dialect
lombok
```

## Estrutura do Projeto

```
java/male/
├── pom.xml
├── src/main/java/com/thz/male/
│   ├── MaleApplication.java
│   ├── config/
│   │   ├── AiConfig.java
│   │   ├── WebSocketConfig.java
│   │   └── DatabaseConfig.java
│   ├── model/
│   │   ├── Conversation.java
│   │   ├── Message.java
│   │   ├── TopicMemory.java
│   │   ├── AgentSkill.java
│   │   ├── ArgumentScore.java
│   │   ├── DebateState.java
│   │   └── AgentDecision.java
│   ├── repository/
│   │   ├── ConversationRepository.java
│   │   ├── MessageRepository.java
│   │   ├── TopicMemoryRepository.java
│   │   ├── AgentSkillRepository.java
│   │   ├── ArgumentScoreRepository.java
│   │   └── DebateStateRepository.java
│   ├── agent/
│   │   ├── AgentPersona.java
│   │   ├── AgentSoul.java
│   │   └── AgentMemory.java
│   ├── engine/
│   │   ├── MultiAgentEngine.java
│   │   ├── SpeakerSelector.java
│   │   ├── LoopDetector.java
│   │   ├── QualityMonitor.java
│   │   ├── MetaModerator.java
│   │   └── ConversationSummarizer.java
│   ├── service/
│   │   ├── DebateService.java
│   │   ├── TopicService.java
│   │   ├── ModelService.java
│   │   └── SessionService.java
│   ├── controller/
│   │   ├── WebController.java
│   │   ├── DebateWebSocketHandler.java
│   │   └── RestApiController.java
│   └── guardrails/
│       └── ScopeGuard.java
├── src/main/resources/
│   ├── application.yml
│   ├── schema.sql
│   ├── templates/
│   │   ├── index.html
│   │   ├── debate.html
│   │   └── history.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
```

## Mapeamento Schema Python -> Java Entity

| Tabela Python | Entity Java | Colunas mantidas |
|---------------|-------------|------------------|
| `conversations` | `Conversation` | id, topic, session_id, summary_short, summary_full, created_at |
| `messages` | `Message` | id, conversation_id, agent_name, content, status, turn, idempotency_key, created_at |
| `topic_memory` | `TopicMemory` | id, topic (UNIQUE), category, times_discussed, last_consensus, last_discussed_at, created_at |
| `agent_skills` | `AgentSkill` | id, agent_name, skill_domain, expertise_level, times_applied, consensus_contributions, created_at |
| `argument_scores` | `ArgumentScore` | id, message_id, conversation_id, agent_name, quality_score, novelty_score, expertise_alignment, overall_score, created_at |
| `debate_state` | `DebateState` | conversation_id (PK), topic, current_turn, history_json, status, session_id, created_at, updated_at |

## Mapeamento Python -> Java

| Python | Java | Notas |
|--------|------|-------|
| `server.py` (FastAPI) | `MultiAgentEngine.java` + controllers | FSM do orquestrador |
| `agents/soul.py` | `AgentSoul.java` | SOUL.md persistente |
| `agents/memory.py` | `AgentMemory.java` | Memoria episodica |
| `stability/speaker_selector.py` | `SpeakerSelector.java` | Turnos por leilao |
| `stability/loop_detector.py` | `LoopDetector.java` | Anti-ciclos |
| `stability/quality_monitor.py` | `QualityMonitor.java` | DAR + bigramas |
| `stability/meta_moderator.py` | `MetaModerator.java` | Moderacao |
| `stability/conversation_summarizer.py` | `ConversationSummarizer.java` | Resumos |
| `config.py` | `application.yml` | Configuracao |
| `gui.py` (Tkinter) | Thymeleaf + WebSocket | UI web |

## Ordem de Implementacao

| Fase | O que | Arquivos |
|------|-------|----------|
| 1 | Scaffold Maven | `pom.xml`, `application.yml`, `MaleApplication.java` |
| 2 | SQLite + JPA | `schema.sql`, entities, repositories |
| 3 | Spring AI + Identidade | `AiConfig`, `AgentSoul`, `AgentDecision` |
| 4 | Personas | `AgentPersona` (9 personas), `AgentMemory` |
| 5 | FSM Core | `MultiAgentEngine`, `SpeakerSelector`, `LoopDetector` |
| 6 | Stability | `QualityMonitor`, `MetaModerator`, `ConversationSummarizer` |
| 7 | WebSocket | `WebSocketConfig`, `DebateWebSocketHandler` |
| 8 | Services | `DebateService`, `TopicService`, `ModelService`, `SessionService` |
| 9 | Controllers | `WebController`, `RestApiController` |
| 10 | UI | Templates Thymeleaf + CSS dark theme + JS STOMP |

## Como o ChatClient do Spring AI e usado

```java
// Config
@Configuration
public class AiConfig {
    @Bean
    ChatClient chatClient(ChatClient.Builder builder) {
        return builder.build();
    }
}

// Chamada simples
String response = chatClient.prompt()
    .system(agent.getSystemPrompt())
    .user(userPrompt)
    .options(OllamaChatOptions.builder()
        .model(agent.getModel())
        .temperature(agent.getTemperature())
        .build())
    .call()
    .content();
```

## WebSocket STOMP Flow

```
Browser                    Spring Boot                 Ollama
  |                            |                          |
  |-- CONNECT /ws ------------>|                          |
  |-- SUBSCRIBE /topic/debate  |                          |
  |-- SEND /app/debate/start ->|                          |
  |                            |-- ChatClient.call() ---->|
  |<-- /topic/debate/turn -----|<-- response -------------|
  |<-- /topic/debate/turn -----|                          |
  |     ... (repete por turno) |                          |
  |<-- /topic/debate/complete -|                          |
```

## Referencias

- Spring AI Ollama: https://docs.spring.io/spring-ai/reference/2.0-SNAPSHOT/api/chat/ollama-chat.html
- Config Ollama: http://127.0.0.1:11434
- Modelos: qwen2.5:7b (default), qwen3.5:9b (fast), gemma4:12b-it-qat (primary), gemma4:26b-a4b-it-qat (supervisor)
