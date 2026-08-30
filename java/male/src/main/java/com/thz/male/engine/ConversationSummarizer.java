package com.thz.male.engine;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.ollama.api.OllamaOptions;

import java.util.*;

/**
 * Responsável por criar resumos da conversa e fornecer contexto para os agentes.
 */
public class ConversationSummarizer {

    private final ChatClient chatClient;
    private final String model;
    private int lastSummaryTurn = 0;
    private String cachedSummary = "";

    /**
     * Construtor do ConversationSummarizer
     * @param chatClient ChatClient para comunicação com o LLM
     * @param model Modelo a ser usado
     */
    public ConversationSummarizer(ChatClient chatClient, String model) {
        this.chatClient = chatClient;
        this.model = model;
    }

    /**
     * Retorna o resumo da conversa, ou cria um se não existir.
     * @param history Histórico da conversa
     * @param currentTurn Turno atual
     * @param interval Intervalo entre resumos
     * @return Resumo da conversa
     */
    public String getOrCreateSummary(List<Map<String, Object>> history, int currentTurn, int interval) {
        if (currentTurn - lastSummaryTurn < interval && !cachedSummary.isEmpty()) {
            return cachedSummary;
        }

        if (history.size() < 3) {
            return buildSimpleSummary(history);
        }

        List<Map<String, Object>> recentHistory = history.subList(
                Math.max(0, history.size() - 12), history.size());

        StringBuilder transcript = new StringBuilder();
        for (Map<String, Object> h : recentHistory) {
            transcript.append("[").append(h.get("author")).append("]: ");
            String content = (String) h.getOrDefault("content", "");
            if (content.length() > 200)
                content = content.substring(0, 200) + "...";
            transcript.append(content).append("\n");
        }

        String prompt = "Gere um RESUMO CONCISO deste debate tecnico em andamento.\n" +
                "Max 5 linhas. Destaque:\n" +
                "- Principais argumentos de cada lado\n" +
                "- Pontos de acordo e desacordo\n" +
                "- Status atual do debate\n\n" +
                "Transcript:\n" + transcript + "\n\n" +
                "Resumo:";

        try {
            cachedSummary = chatClient.prompt()
                    .user(prompt)
                    .options(OllamaOptions.builder().model(model).temperature(0.3).build())
                    .call()
                    .content();
            lastSummaryTurn = currentTurn;
            return cachedSummary;
        } catch (Exception e) {
            return buildSimpleSummary(history);
        }
    }

    /**
     * Retorna o último argumento do histórico
     * @param history Histórico da conversa
     * @return Último argumento do histórico
     */
    public String getLastArgumentContext(List<Map<String, Object>> history) {
        if (history.isEmpty())
            return "Nenhum argumento ainda.";

        Map<String, Object> last = history.get(history.size() - 1);
        Map<String, Object> secondLast = history.size() >= 2 ? history.get(history.size() - 2) : null;

        StringBuilder sb = new StringBuilder("## Contexto Imediato\n");
        if (secondLast != null) {
            String prevContent = (String) secondLast.getOrDefault("content", "");
            if (prevContent.length() > 200)
                prevContent = prevContent.substring(0, 200) + "...";
            sb.append("Ultimo argumento de ").append(secondLast.get("author")).append(":\n");
            sb.append(prevContent).append("\n\n");
        }

        String lastContent = (String) last.getOrDefault("content", "");
        if (lastContent.length() > 200)
            lastContent = lastContent.substring(0, 200) + "...";
        sb.append("Argumento mais recente de ").append(last.get("author")).append(":\n");
        sb.append(lastContent);
        return sb.toString();
    }

    /**
     * Retorna um resumo simples da conversa
     * @param history Histórico da conversa
     * @return Resumo simples da conversa
     */
    private String buildSimpleSummary(List<Map<String, Object>> history) {
        if (history.isEmpty())
            return "Nenhum argumento ainda.";

        Set<String> agents = new LinkedHashSet<>();
        for (Map<String, Object> h : history) {
            agents.add((String) h.get("author"));
        }

        long agreeCount = history.stream()
                .filter(h -> "agree".equals(h.getOrDefault("vote", "abstain")))
                .count();
        long disagreeCount = history.stream()
                .filter(h -> "disagree".equals(h.getOrDefault("vote", "abstain")))
                .count();

        return "Turnos: " + history.size() +
                " | Agentes: " + String.join(", ", agents) +
                " | Agree: " + agreeCount +
                " | Disagree: " + disagreeCount;
    }
}
