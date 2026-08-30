package com.thz.male.engine;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.ollama.api.OllamaOptions;

import java.util.*;

/**
 * Modera o debate e decide quando finalizar ou forçar votação.
 */
public class MetaModerator {

    private final ChatClient chatClient;
    private final String model;
    private int lastActionTurn = 0;

    public MetaModerator(ChatClient chatClient, String model) {
        this.chatClient = chatClient;
        this.model = model;
    }

    /**
     * Verifica se o debate deve continuar
     * @param history Histórico do debate
     * @param health Saúde do debate
     * @param currentTurn Turno atual
     * @return Mapa com ação (continue, finalize, force_vote) e razão
     */
    public Map<String, Object> shouldContinue(
            List<Map<String, Object>> history,
            Map<String, Object> health,
            int currentTurn) {

        Map<String, Object> result = new HashMap<>();
        result.put("action", "continue");
        result.put("reason", "");

        if (currentTurn - lastActionTurn < 3)
            return result;

        double diversity = (double) health.getOrDefault("diversityScore", 1.0);
        int repetitivos = (int) health.getOrDefault("repetitionCount", 0);
        int conformidade = (int) health.getOrDefault("conformityCount", 0);

        if (history.size() >= 8 && diversity < 0.35) {
            result.put("action", "finalize");
            result.put("reason", "Debate com baixa diversidade. Sintetizando conclusao.");
            lastActionTurn = currentTurn;
            return result;
        }

        if (history.size() >= 6 && repetitivos >= 3) {
            result.put("action", "force_vote");
            result.put("reason", "Repeticao detectada. Forcando votacao.");
            lastActionTurn = currentTurn;
            return result;
        }

        if (conformidade >= 7) {
            result.put("action", "force_vote");
            result.put("reason", "Alta conformidade. Time ja convergiu.");
            lastActionTurn = currentTurn;
            return result;
        }

        if (currentTurn >= 20) {
            result.put("action", "finalize");
            result.put("reason", "Numero maximo de turnos atingido.");
            lastActionTurn = currentTurn;
            return result;
        }

        return result;
    }

    /**
     * Sintetiza a conclusão do debate
     * @param history Histórico do debate
     * @param topic Tópico do debate
     * @return Resumo do debate
     */
    public String synthesizeFinal(List<Map<String, Object>> history, String topic) {
        StringBuilder transcript = new StringBuilder();
        for (Map<String, Object> h : history) {
            transcript.append("[").append(h.get("author")).append("]: ");
            String content = (String) h.getOrDefault("content", "");
            if (content.length() > 200)
                content = content.substring(0, 200) + "...";
            transcript.append(content).append("\n");
        }

        String prompt = "Gere um resumo CONCISO deste debate tecnico entre agentes de IA.\n" +
                "Formato OBRIGATORIO (max 5 linhas):\n" +
                "- Topico: ...\n" +
                "- Posicoes principais: ... (2-3 pontos de cada lado)\n" +
                "- Consenso: ... (ou 'Sem consenso' se houve divergencia)\n" +
                "- Aprendizado chave: ... (1 insight principal)\n\n" +
                "Topico: " + topic + "\n\n" +
                "Transcript:\n" + transcript + "\n\n" +
                "Resumo:";

        try {
            return chatClient.prompt()
                    .user(prompt)
                    .options(OllamaOptions.builder().model(model).temperature(0.3).build())
                    .call()
                    .content();
        } catch (Exception e) {
            return "Resumo nao disponivel.";
        }
    }

    public void reset() {
        lastActionTurn = 0;
    }
}
