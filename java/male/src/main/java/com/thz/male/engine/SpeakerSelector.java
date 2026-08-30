package com.thz.male.engine;

import java.util.*;

import com.thz.male.agent.AgentPersona;

/**
 * Seleciona os próximos agentes a falar no debate.
 */
public class SpeakerSelector {

    private final Map<String, Integer> speakingHistory = new HashMap<>();
    private final List<Map<String, String>> questionQueue = new ArrayList<>();

    /**
     * Seleciona os próximos agentes a falar
     * @param agents Lista de agentes disponíveis
     * @param history Histórico do debate
     * @param currentTurn Turno atual
     * @param maxSpeakers Número máximo de agentes a selecionar
     * @param pendingQuestions Perguntas pendentes
     * @return Lista de agentes selecionados
     */
    public List<String> selectNextSpeakers(
            List<AgentPersona> agents,
            List<Map<String, Object>> history,
            int currentTurn,
            int maxSpeakers,
            List<Map<String, String>> pendingQuestions) {

        if (agents.isEmpty())
            return List.of();

        if (!history.isEmpty()) {
            String lastSpeaker = (String) history.get(history.size() - 1).get("author");
            for (String name : speakingHistory.keySet()) {
                speakingHistory.put(name, speakingHistory.getOrDefault(name, 0) + 1);
            }
            speakingHistory.put(lastSpeaker, 0);
        }

        List<String> selected = new ArrayList<>();

        if (pendingQuestions != null) {
            List<String> agentNames = agents.stream().map(AgentPersona::name).toList();
            for (Map<String, String> q : pendingQuestions) {
                String to = q.get("to");
                if (agentNames.contains(to) && !selected.contains(to)) {
                    selected.add(to);
                    if (selected.size() >= maxSpeakers)
                        return selected;
                }
            }
        }

        List<AgentPersona> candidates = agents.stream()
                .filter(a -> !selected.contains(a.name()))
                .toList();

        Map<String, Integer> bids = new HashMap<>();
        for (AgentPersona agent : candidates) {
            bids.put(agent.name(), calculateBid(agent, history, currentTurn));
        }

        List<Map.Entry<String, Integer>> sortedBids = bids.entrySet().stream()
                .sorted((a, b) -> b.getValue() - a.getValue())
                .toList();

        for (Map.Entry<String, Integer> entry : sortedBids) {
            if (selected.size() >= maxSpeakers)
                break;
            if (entry.getValue() >= 3) {
                selected.add(entry.getKey());
            }
        }

        if (selected.isEmpty() && !candidates.isEmpty()) {
            AgentPersona leastRecent = candidates.stream()
                    .min(Comparator.comparingInt(a -> speakingHistory.getOrDefault(a.name(), 999)))
                    .orElse(candidates.get(0));
            selected.add(leastRecent.name());
        }

        return selected.subList(0, Math.min(maxSpeakers, selected.size()));
    }

    /**
     * Calcula o bid de um agente
     * @param agent Agente
     * @param history Histórico do debate
     * @param currentTurn Turno atual
     * @return Bid do agente
     */
    private int calculateBid(AgentPersona agent, List<Map<String, Object>> history, int currentTurn) {
        if (history.isEmpty())
            return 8;

        String lastContent = ((String) history.get(history.size() - 1).getOrDefault("content", "")).toLowerCase();

        int expertiseScore = 0;
        for (String kw : agent.expertiseKeywords()) {
            if (lastContent.contains(kw.toLowerCase())) {
                expertiseScore++;
            }
        }
        expertiseScore = Math.min(4, expertiseScore);

        int turnsSince = speakingHistory.getOrDefault(agent.name(), 999);
        int recencyScore = Math.min(3, turnsSince / 2);

        int addressScore = 0;
        if (lastContent.contains(agent.name().toLowerCase())) {
            addressScore = 3;
        } else if (lastContent.contains("pergunto") || lastContent.contains("questiono")
                || lastContent.contains("discordo")) {
            addressScore = 1;
        }

        int total = expertiseScore + recencyScore + addressScore;
        total = Math.max(1, Math.min(10, total + new Random().nextInt(3) - 1));
        return total;
    }

    /**
     * Adiciona uma pergunta ao sistema
     * @param fromAgent Agente que fez a pergunta
     * @param toAgent Agente que deve responder
     * @param question Pergunta
     */
    public void addQuestion(String fromAgent, String toAgent, String question) {
        questionQueue.add(Map.of("from", fromAgent, "to", toAgent, "question", question));
    }

    /**
     * Retorna a próxima pergunta para um agente
     * @param forAgent Agente
     * @return Próxima pergunta
     */
    public Map<String, String> getPendingQuestion(String forAgent) {
        return questionQueue.stream()
                .filter(q -> q.get("to").equals(forAgent))
                .findFirst()
                .orElse(null);
    }

    /**
     * Remove a pergunta respondida
     * @param toAgent Agente que respondeu
     */
    public void clearAnsweredQuestion(String toAgent) {
        questionQueue.removeIf(q -> q.get("to").equals(toAgent));
    }

    /**
     * Reseta o sistema
     */
    public void reset() {
        speakingHistory.clear();
        questionQueue.clear();
    }
}
