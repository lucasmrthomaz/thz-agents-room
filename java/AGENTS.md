# Mauricio (Multi-Agent Local Engine) in SpringBoot AI

## Stack
- Spring Boot 3.4.x + Spring AI 1.0.0
- Ollama (localhost:11434)
- SQLite (compativel com thz-room-cortex.db do Python)
- Thymeleaf + WebSocket STOMP
- Java 25 (GraalVM CE 25.0.2)
- Virtual Threads habilitado

## Estrutura

```
java/mauricio/
├── pom.xml
├── src/main/java/com/thz/mauricio/
│   ├── MaleApplication.java
│   ├── config/
│   │   ├── AiConfig.java              # ChatClient bean (Ollama)
│   │   ├── WebSocketConfig.java        # STOMP + SockJS
│   │   └── DatabaseConfig.java         # SQLite + JPA
│   ├── model/                          # JPA Entities
│   ├── repository/                     # Spring Data JPA
│   ├── agent/                          # Personas, Soul, Memory
│   ├── engine/                         # FSM orquestrador
│   ├── service/                        # Business logic
│   ├── controller/                     # Web + REST + WebSocket
│   └── guardrails/                     # Validacao de topicos
├── src/main/resources/
│   ├── application.yml
│   ├── schema.sql
│   ├── templates/                      # Thymeleaf
│   └── static/                         # CSS + JS
```

## Rodar

```bash
cd java/mauricio
mvn spring-boot:run
```

Acessar: http://localhost:9983

## Roadmap
Ver [roadmap.md](roadmap.md) para detalhes completos.

### GraalVM Native Image (futuro)
- Compilar para binário nativo (~50ms startup, ~50-80MB RAM)
- Requer configuracao de reflect-config, proxy-config para Spring AI + JPA + WebSocket
- Spring Boot 3.x tem suporte via spring-graalvm-native
- Spring AI ainda nao garante 100% compatibilidade
- Pendente: validar compatibilidade antes de migrar
