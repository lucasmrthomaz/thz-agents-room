package com.thz.male.engine;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.ollama.api.OllamaOptions;

import java.util.Arrays;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.thz.male.agent.AgentMemory;
import com.thz.male.agent.AgentPersona;
import com.thz.male.agent.AgentSoul;
import com.thz.male.config.DatabaseConfig;
import com.thz.male.model.*;
import com.thz.male.repository.*;

import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Orquestra o debate entre múltiplos agentes.
 */
public class MultiAgentEngine {

    private static final Logger log = LoggerFactory.getLogger(MultiAgentEngine.class);
    private static final ObjectMapper objectMapper = new ObjectMapper();
    private static final Pattern JSON_BLOCK_PATTERN = Pattern.compile("```(?:json)?\\s*\\n?(\\{.*?\\})\\s*\\n?```", Pattern.DOTALL);

    private final ChatClient chatClient;
    private final DatabaseConfig config;
    private final ConversationRepository conversationRepo;
    private final MessageRepository messageRepo;
    private final ArgumentScoreRepository argumentScoreRepo;
    private final TopicMemoryRepository topicMemoryRepo;
    private final DebateStateRepository debateStateRepo;
    private final AgentSkillRepository agentSkillRepo;

    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
    private final SpeakerSelector speakerSelector = new SpeakerSelector();
    private final LoopDetector loopDetector = new LoopDetector();

    private List<AgentPersona> agents;
    private String model;

    public MultiAgentEngine(
            ChatClient chatClient,
            DatabaseConfig config,
            ConversationRepository conversationRepo,
            MessageRepository messageRepo,
            TopicMemoryRepository topicMemoryRepo,
            ArgumentScoreRepository argumentScoreRepo,
            DebateStateRepository debateStateRepo,
            AgentSkillRepository agentSkillRepo) {
        this.chatClient = chatClient;
        this.config = config;
        this.conversationRepo = conversationRepo;
        this.messageRepo = messageRepo;
        this.topicMemoryRepo = topicMemoryRepo;
        this.argumentScoreRepo = argumentScoreRepo;
        this.debateStateRepo = debateStateRepo;
        this.agentSkillRepo = agentSkillRepo;
    }

    public void setAgents(List<AgentPersona> agents) {
        this.agents = agents;
    }

    public void setModel(String model) {
        this.model = model;
    }

    /**
     * Executa o debate entre múltiplos agentes.
     * @param conversationId ID da conversa
     * @param topic Tópico do debate
     * @param sessionId ID da sessão
     * @param callback Callback de eventos
     * @return Resultado do debate
     */
    public DebateResult executeDebate(String conversationId, String topic, String sessionId,
            OnEventCallback callback) {
        conversationRepo.save(new Conversation(conversationId, topic, sessionId));

        List<Map<String, Object>> history = new ArrayList<>();
        int currentTurn = 0;
        speakerSelector.reset();

        Path dataDir = Path.of("../data");

        while (currentTurn < config.getMaxTurns()) {
            List<String> nextSpeakers = speakerSelector.selectNextSpeakers(
                    agents, history, currentTurn, 3, null);

            for (String agentName : nextSpeakers) {
                AgentPersona agent = agents.stream()
                        .filter(a -> a.name().equals(agentName))
                        .findFirst()
                        .orElse(null);
                if (agent == null)
                    continue;

                currentTurn++;
                callback.onEvent("turn_start", Map.of(
                        "turn", currentTurn,
                        "agent", agent.name(),
                        "role", agent.roleTitle()));

                String transcript = buildTranscript(history, topic);

                String instruction;
                if (currentTurn == 1) {
                    instruction = "Voce abre o debate. Apresente sua tese tecnica inicial sobre o problema.";
                } else {
                    instruction = "Analise o argumento do turno anterior e responda de forma critica, apontando pros/contras e trazendo dados concretos.";
                }

                Map<String, Object> health = loopDetector.analyzeDebateHealth(history);
                String antiConform = loopDetector.getAntiConformityInstruction(health, agent.roleTitle());
                instruction += antiConform;

                AgentSoul soul = new AgentSoul(agent.name(), dataDir);
                String systemPrompt = agent.buildSystemPrompt();
                if (soul.exists()) {
                    String personality = soul.getPersonalitySummary();
                    if (!personality.isEmpty()) {
                        systemPrompt += "\n\n" + personality;
                    }
                }

                AgentMemory memory = new AgentMemory(agent.name(), dataDir);
                String semantic = memory.getSemanticSummary();
                if (!semantic.isEmpty()) {
                    systemPrompt += "\n\n" + semantic;
                }

                String userPrompt = "Topico da Discusso: " + topic + "\n\n" +
                        transcript + "\n\n" + instruction + "\n" +
                        "Status: 'CONTINUE' para contra-argumentar; 'CONSENSUS' quando concordar com a maioria dos pontos principais.\n"
                        +
                        "Vote: 'agree' se concorda com o argumento anterior, 'disagree' se discorda, 'abstain' se neutro.\n";

                AgentDecision decision = callOllama(systemPrompt, userPrompt, agent);

                String effectiveStatus = decision.status();
                if (currentTurn < config.getMinTurns() && "CONSENSUS".equals(effectiveStatus)) {
                    effectiveStatus = "CONTINUE";
                }

                Map<String, Object> quality = monitorQuality(decision.argument(), history, agent.roleTitle());
                double overallScore = (double) quality.getOrDefault("overallScore", 1.0);
                if (overallScore < 0.2 && currentTurn > config.getMinTurns()) {
                    effectiveStatus = "CONTINUE";
                }

                messageRepo.save(
                        new Message(conversationId, agent.name(), decision.argument(), effectiveStatus, currentTurn));

                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("author", agent.name());
                entry.put("content", decision.argument());
                entry.put("turn", currentTurn);
                entry.put("status", effectiveStatus);
                entry.put("vote", decision.vote() != null ? decision.vote() : "abstain");
                history.add(entry);

                argumentScoreRepo.save(new ArgumentScore(
                        UUID.randomUUID().toString(), conversationId, agent.name(),
                        (double) quality.getOrDefault("noveltyScore", 0.5),
                        (double) quality.getOrDefault("noveltyScore", 0.5),
                        (double) quality.getOrDefault("expertiseAlignment", 0.5),
                        overallScore));

                callback.onEvent("turn_end", Map.of(
                        "turn", currentTurn,
                        "agent", agent.name(),
                        "role", agent.roleTitle(),
                        "argument", decision.argument(),
                        "status", effectiveStatus,
                        "vote", decision.vote() != null ? decision.vote() : "abstain"));

                if ("FORCE_STOP".equals(effectiveStatus)) {
                    return new DebateResult(false, "force_stop", currentTurn, history);
                }

                if (currentTurn >= config.getMinTurns()) {
                    long votesAgree = history.stream()
                            .skip(Math.max(0, history.size() - 9))
                            .filter(h -> "agree".equals(h.getOrDefault("vote", "abstain"))
                                    || "CONSENSUS".equals(h.getOrDefault("status", "")))
                            .count();

                    if (votesAgree >= config.getConsensusThreshold()) {
                        return new DebateResult(true, "voting_consensus", currentTurn, history);
                    }
                }

                if (currentTurn >= config.getMaxTurns())
                    break;
            }
            if (currentTurn >= config.getMaxTurns())
                break;
        }

        return new DebateResult(false, "max_turns_reached", currentTurn, history);
    }

    /**
     * Calcula a qualidade de um argumento
     * @param argument Argumento a ser analisado
     * @param history Histórico da conversa
     * @param agentRole Papel do agente
     * @return Mapa com métricas de qualidade
     */
    private AgentDecision callOllama(String systemPrompt, String userPrompt, AgentPersona agent) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Future<String> future = executor.submit(() -> {
                    return chatClient.prompt()
                            .system(systemPrompt)
                            .user(userPrompt)
                        .options(OllamaOptions.builder()
                                .model(model)
                                .numCtx(config.getNumCtx())
                                .temperature(agent.temperature())
                                .build())
                            .call()
                            .content();
                });

                String response = future.get(120, TimeUnit.SECONDS);
                if (response == null || response.trim().isEmpty()) {
                    log.warn("Resposta vazia de {} (tentativa {}/2)", agent.name(), attempt);
                    if (attempt < 2) {
                        Thread.sleep(1000);
                        continue;
                    }
                    return new AgentDecision(
                            "O modelo nao gerou resposta para " + agent.name() + ".",
                            "CONTINUE", "abstain", null, null);
                }
                return parseDecision(response);

            } catch (TimeoutException e) {
                log.error("Timeout ao chamar Ollama para agente {} (120s)", agent.name());
                return new AgentDecision(
                        "Timeout na inferencia do agente " + agent.name() + ". Ollama nao respondeu a tempo.",
                        "CONTINUE", "abstain", null, null);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return new AgentDecision(
                        "Interrompido ao chamar Ollama para " + agent.name(),
                        "CONTINUE", "abstain", null, null);
            } catch (Exception e) {
                log.error("Erro ao chamar Ollama para agente {}: {}", agent.name(), e.getMessage());
                return new AgentDecision(
                        "Erro ao conectar com Ollama: " + e.getMessage(),
                        "CONTINUE", "abstain", null, null);
            }
        }
        return new AgentDecision("Falha ao obter resposta de " + agent.name(),
                "CONTINUE", "abstain", null, null);
    }

    /**
     * Analisa a decisão do agente
     * @param response Resposta do agente
     * @return Decisão do agente
     */
    private AgentDecision parseDecision(String response) {
        try {
            String json = response.trim();
            String jsonString = extractJsonFromResponse(json);
            if (jsonString != null && jsonString.contains("\"argument\"")) {
                JsonNode node = objectMapper.readTree(jsonString);
                String argument = node.has("argument") ? node.get("argument").asText() : null;
                String status = node.has("status") ? node.get("status").asText() : "CONTINUE";
                String vote = node.has("vote") ? node.get("vote").asText() : "abstain";
                String questionTo = node.has("question_to") ? node.get("question_to").asText(null) : null;
                String reasoning = node.has("reasoning") ? node.get("reasoning").asText(null) : null;
                return new AgentDecision(argument, status, vote, questionTo, reasoning);
            }
            return new AgentDecision(response, "CONTINUE", "abstain", null, null);
        } catch (Exception e) {
            log.debug("Falha ao parsear JSON, usando resposta como texto puro: {}", e.getMessage());
            return new AgentDecision(response, "CONTINUE", "abstain", null, null);
        }
    }

    /**
     * Extrai JSON da resposta
     * @param response Resposta
     * @return JSON extraído
     */
    private String extractJsonFromResponse(String response) {
        Matcher matcher = JSON_BLOCK_PATTERN.matcher(response);
        if (matcher.find()) {
            return matcher.group(1);
        }
        int braceStart = response.indexOf('{');
        int braceEnd = response.lastIndexOf('}');
        if (braceStart >= 0 && braceEnd > braceStart) {
            return response.substring(braceStart, braceEnd + 1);
        }
        return null;
    }

    /**
     * Constrói o histórico do debate
     * @param history Histórico do debate
     * @param topic Tópico do debate
     * @return Resumo do debate
     */
    private String buildTranscript(List<Map<String, Object>> history, String topic) {
        if (history.isEmpty())
            return "Topico: " + topic + "\nNenhum argumento ainda.";

        int maxHistory = 8;
        List<Map<String, Object>> recent = history.size() > maxHistory
                ? history.subList(history.size() - maxHistory, history.size())
                : history;

        StringBuilder sb = new StringBuilder("## Resumo da Discusso\n");
        for (Map<String, Object> h : recent) {
            sb.append("[").append(h.get("author")).append(" - Turno ").append(h.get("turn")).append("]: ");
            String content = (String) h.get("content");
            if (content == null || content.isEmpty()) {
                content = "(sem argumento)";
            } else if (content.length() > 300) {
                content = content.substring(0, 300) + "...";
            }
            sb.append(content).append("\n");
        }
        return sb.toString();
    }

    /**
     * Monitora a qualidade de um argumento
     * @param argument Argumento a ser analisado
     * @param history Histórico do debate
     * @param agentRole Papel do agente
     * @return Mapa com métricas de qualidade
     */
    private Map<String, Object> monitorQuality(String argument, List<Map<String, Object>> history, String agentRole) {
        Map<String, Object> quality = new HashMap<>();
        if (argument == null || argument.trim().isEmpty()) {
            quality.put("wordCount", 0);
            quality.put("isTooShort", true);
            quality.put("noveltyScore", 0.0);
            quality.put("expertiseAlignment", 0.0);
            quality.put("overallScore", 0.0);
            return quality;
        }

        int wordCount = argument.split("\\s+").length;
        quality.put("wordCount", wordCount);
        quality.put("isTooShort", wordCount < 20);

        double noveltyScore = 0.5;
        if (history.size() >= 3) {
            Set<String> argWords = new HashSet<>(Arrays.asList(argument.toLowerCase().split("\\s+")));
            for (Map<String, Object> h : history) {
                String prev = ((String) h.getOrDefault("content", "")).toLowerCase();
                Set<String> prevWords = new HashSet<>(Arrays.asList(prev.split("\\s+")));
                Set<String> intersection = new HashSet<>(argWords);
                intersection.retainAll(prevWords);
                if (!prevWords.isEmpty()) {
                    noveltyScore -= (double) intersection.size() / prevWords.size() * 0.1;
                }
            }
            noveltyScore = Math.max(0, Math.min(1, noveltyScore));
        }
        quality.put("noveltyScore", noveltyScore);
        quality.put("expertiseAlignment", 0.7);
        quality.put("overallScore", noveltyScore * 0.5 + 0.5 * 0.5);
        return quality;
    }

    /**
     * Resultado do debate
     * @param consensus Se houve consenso
     * @param reason Motivo do resultado
     * @param totalTurns Número total de turnos
     * @param history Histórico do debate
     */
    public record DebateResult(boolean consensus, String reason, int totalTurns, List<Map<String, Object>> history) {
    }

    /**
     * Callback de eventos
     */
    public interface OnEventCallback {
        /**
         * Evento do debate
         * @param event Evento
         * @param data Dados do evento
         */
        void onEvent(String event, Map<String, Object> data);
    }
}
