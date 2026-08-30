package com.thz.male.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

import com.thz.male.agent.AgentPersona;
import com.thz.male.config.DatabaseConfig;
import com.thz.male.engine.MultiAgentEngine;
import com.thz.male.repository.*;
import com.thz.male.service.ModelService;
import com.thz.male.service.TopicService;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.*;

/**
 * WebSocket handler para debates
 * - Inicia debates
 * - Para debates
 * - Envia eventos para o front
 */
@Controller
public class DebateWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(DebateWebSocketHandler.class);

    private final ChatClient chatClient;
    private final DatabaseConfig config;
    private final ConversationRepository conversationRepo;
    private final MessageRepository messageRepo;
    private final TopicMemoryRepository topicMemoryRepo;
    private final ArgumentScoreRepository argumentScoreRepo;
    private final DebateStateRepository debateStateRepo;
    private final AgentSkillRepository agentSkillRepo;
    private final SimpMessagingTemplate messagingTemplate;
    private final ModelService modelService;
    private final TopicService topicService;

    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
    private volatile boolean autonomousRunning = false;
    private volatile Future<?> autonomousFuture = null;

    public DebateWebSocketHandler(
            ChatClient chatClient,
            DatabaseConfig config,
            ConversationRepository conversationRepo,
            MessageRepository messageRepo,
            TopicMemoryRepository topicMemoryRepo,
            ArgumentScoreRepository argumentScoreRepo,
            DebateStateRepository debateStateRepo,
            AgentSkillRepository agentSkillRepo,
            SimpMessagingTemplate messagingTemplate,
            ModelService modelService,
            TopicService topicService) {
        this.chatClient = chatClient;
        this.config = config;
        this.conversationRepo = conversationRepo;
        this.messageRepo = messageRepo;
        this.topicMemoryRepo = topicMemoryRepo;
        this.argumentScoreRepo = argumentScoreRepo;
        this.debateStateRepo = debateStateRepo;
        this.agentSkillRepo = agentSkillRepo;
        this.messagingTemplate = messagingTemplate;
        this.modelService = modelService;
        this.topicService = topicService;
    }

    @MessageMapping("/debate/start")
    public void startDebate(Map<String, Object> payload) {
        String mode = String.valueOf(payload.getOrDefault("mode", "single"));
        log.info("[WS] Recebido startDebate mode={}", mode);

        executor.submit(() -> {
            try {
                if ("single".equals(mode)) {
                    handleSingleDebate(payload);
                } else if ("autonomous".equals(mode)) {
                    handleAutonomousSession(payload);
                }
            } catch (Exception e) {
                log.error("[WS] Erro no debate: {}", e.getMessage(), e);
                sendEvent("error", Map.of("message", "Erro: " + e.getMessage()));
            }
        });
    }
    
    @MessageMapping("/debate/stop")
    public void stopDebate() {
        log.info("[WS] Parando sessao autonomo");
        autonomousRunning = false;
        if (autonomousFuture != null) {
            autonomousFuture.cancel(true);
        }
        sendEvent("session_stopped", Map.of());
    }

    private void handleSingleDebate(Map<String, Object> payload) {
        String topic = String.valueOf(payload.get("topic"));
        String requestedModel = String.valueOf(payload.getOrDefault("model", "auto"));
        int maxTurns = toInt(payload.get("maxTurns"), config.getMaxTurns());

        String resolvedModel = modelService.resolveModel(requestedModel);
        log.info("[SINGLE] Topico: {} | Modelo: {}", topic, resolvedModel);

        sendEvent("debate_start", Map.of("topic", topic, "model", resolvedModel));

        try {
            MultiAgentEngine engine = createEngine(resolvedModel);
            String conversationId = UUID.randomUUID().toString();

            MultiAgentEngine.DebateResult result = engine.executeDebate(
                    conversationId, topic, null,
                    (event, data) -> sendEvent(event, data));

            topicMemoryRepo.upsertTopicMemory(topic, result.consensus());

            sendEvent("debate_complete", Map.of(
                    "reason", result.reason(),
                    "totalTurns", result.totalTurns(),
                    "consensus", result.consensus()));

        } catch (Exception e) {
            log.error("[SINGLE] Erro: {}", e.getMessage(), e);
            sendEvent("debate_complete", Map.of(
                    "reason", "error",
                    "totalTurns", 0,
                    "consensus", false,
                    "error", e.getMessage()));
        }
    }

    private void handleAutonomousSession(Map<String, Object> payload) {
        autonomousRunning = true;
        String requestedModel = String.valueOf(payload.getOrDefault("model", "auto"));
        double durationHours = toDouble(payload.get("durationHours"), config.getDurationHours());

        String resolvedModel = modelService.resolveModel(requestedModel);
        String sessionId = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyy-MM-dd_HH-mm"));

        sendEvent("session_start", Map.of(
                "sessionId", sessionId,
                "durationHours", durationHours,
                "model", resolvedModel));

        int debateCount = 0;
        long endTime = System.currentTimeMillis() + (long) (durationHours * 3600 * 1000);

        while (System.currentTimeMillis() < endTime && autonomousRunning) {
            try {
                String topic = topicService.generateTopic(resolvedModel, List.of());
                debateCount++;

                sendEvent("debate_start", Map.of("debateNum", debateCount, "topic", topic));

                MultiAgentEngine engine = createEngine(resolvedModel);
                String conversationId = UUID.randomUUID().toString();

                MultiAgentEngine.DebateResult result = engine.executeDebate(
                        conversationId, topic, sessionId,
                        (event, data) -> sendEvent(event, data));

                topicMemoryRepo.upsertTopicMemory(topic, result.consensus());

                sendEvent("debate_complete", Map.of(
                        "reason", result.reason(),
                        "totalTurns", result.totalTurns(),
                        "consensus", result.consensus()));

                if (System.currentTimeMillis() + 300000 < endTime && autonomousRunning) {
                    sendEvent("debate_paused", Map.of("durationSeconds", 300, "nextDebate", debateCount + 1));
                    long pauseEnd = System.currentTimeMillis() + 300000;
                    while (System.currentTimeMillis() < pauseEnd && autonomousRunning) {
                        Thread.sleep(1000);
                    }
                }

            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                log.error("[AUTONOMOUS] Erro no debate {}: {}", debateCount + 1, e.getMessage());
                sendEvent("error", Map.of("message", "Erro no debate: " + e.getMessage()));
            }
        }

        autonomousRunning = false;
        sendEvent("session_complete", Map.of(
                "sessionId", sessionId,
                "totalDebates", debateCount));
    }

    private MultiAgentEngine createEngine(String model) {
        MultiAgentEngine engine = new MultiAgentEngine(
                chatClient, config, conversationRepo, messageRepo,
                topicMemoryRepo, argumentScoreRepo, debateStateRepo, agentSkillRepo);
        engine.setAgents(AgentPersona.all());
        engine.setModel(model);
        return engine;
    }

    private void sendEvent(String event, Map<String, Object> data) {
        Map<String, Object> msg = new LinkedHashMap<>();
        msg.put("event", event);
        msg.putAll(data);
        log.info("[WS] Enviando evento: {}", event);
        messagingTemplate.convertAndSend("/topic/debate/event", msg);
    }

    private int toInt(Object value, int defaultValue) {
        if (value instanceof Number n)
            return n.intValue();
        try {
            return Integer.parseInt(String.valueOf(value));
        } catch (Exception e) {
            return defaultValue;
        }
    }

    private double toDouble(Object value, double defaultValue) {
        if (value instanceof Number n)
            return n.doubleValue();
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (Exception e) {
            return defaultValue;
        }
    }
}
