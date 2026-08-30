package com.thz.male.engine;

import java.util.*;

/**
 * Detecta loops e padrões repetitivos no debate.
 */
public class LoopDetector {

    private static final Set<String> STOP_WORDS = Set.of(
            "o", "a", "e", "de", "do", "da", "em", "um", "uma", "com", "para",
            "por", "que", "se", "nao", "mais", "como", "tambem", "porem", "ja");

    /**
     * Analisa a saúde do debate
     * @param history Histórico da conversa
     * @return Mapa com a saúde do debate
     */
    public Map<String, Object> analyzeDebateHealth(List<Map<String, Object>> history) {
        Map<String, Object> health = new HashMap<>();
        health.put("diversityScore", 1.0);
        health.put("trend", "diverging");
        health.put("repetitionCount", 0);
        health.put("plagiarismCount", 0);
        health.put("conformityCount", 0);

        if (history.size() < 5)
            return health;

        List<String> contents = history.stream()
                .map(h -> (String) h.getOrDefault("content", ""))
                .toList();

        double diversity = calculateDiversity(contents);
        health.put("diversityScore", diversity);

        int repetitivos = 0;
        for (int i = contents.size() - 5; i < contents.size(); i++) {
            String c1 = contents.get(i).toLowerCase().strip();
            for (int j = i + 1; j < contents.size(); j++) {
                String c2 = contents.get(j).toLowerCase().strip();
                if (c1.length() > 20 && c2.length() > 20) {
                    if (c1.substring(0, Math.min(120, c1.length()))
                            .equals(c2.substring(0, Math.min(120, c2.length())))) {
                        repetitivos++;
                    }
                }
            }
        }
        health.put("repetitionCount", repetitivos);

        long agreeCount = history.stream()
                .filter(h -> "agree".equals(h.getOrDefault("vote", "abstain")))
                .count();
        long disagreeCount = history.stream()
                .filter(h -> "disagree".equals(h.getOrDefault("vote", "abstain")))
                .count();

        if (history.size() >= 6) {
            if (disagreeCount == 0) {
                health.put("conformityCount", (int) agreeCount);
            }
        }

        if (diversity < 0.4) {
            health.put("trend", "repeating");
        } else if (diversity < 0.6) {
            health.put("trend", "converging");
        } else {
            health.put("trend", "diverging");
        }

        return health;
    }

    /**
     * Decide se deve forçar uma ação com base na saúde do debate
     * @param health Saúde do debate
     * @return Ação a ser forçada
     */
    public String shouldForceAction(Map<String, Object> health) {
        double diversity = (double) health.getOrDefault("diversityScore", 1.0);
        int repetitivos = (int) health.getOrDefault("repetitionCount", 0);
        int conformidade = (int) health.getOrDefault("conformityCount", 0);

        if (diversity < 0.3)
            return "end_debate";
        if (diversity < 0.4)
            return "force_vote";
        if (conformidade >= 6)
            return "force_disagreement";
        if (repetitivos >= 3)
            return "redirect_topic";
        return "continue";
    }

    /**
     * Retorna instruções de anti-conformidade para o agente
     * @param health Saúde do debate
     * @param agentRole Papel do agente
     * @return Instruções de anti-conformidade
     */
    public String getAntiConformityInstruction(Map<String, Object> health, String agentRole) {
        double diversity = (double) health.getOrDefault("diversityScore", 1.0);
        int conformidade = (int) health.getOrDefault("conformityCount", 0);

        if (diversity < 0.5 || conformidade >= 5) {
            return "\n\nANTI-CONFORMIDADE: Muitos agentes concordando. " +
                    "Procure um ANGULO DIFERENTE ou DISCORDE de um ponto especifico. " +
                    "Traga uma perspectiva que NINGUEM mencionou ainda.";
        }
        return "";
    }

    /**
     * Calcula a diversidade do debate
     * @param contents Conteúdo do debate
     * @return Diversidade do debate
     */
    private double calculateDiversity(List<String> contents) {
        if (contents.size() < 4)
            return 1.0;

        List<Set<String>> bigramsList = new ArrayList<>();
        for (String content : contents) {
            bigramsList.add(getBigrams(content));
        }

        Set<String> allBigrams = new HashSet<>();
        for (Set<String> bg : bigramsList) {
            allBigrams.addAll(bg);
        }

        if (allBigrams.isEmpty())
            return 1.0;

        Set<String> intersection = new HashSet<>(bigramsList.get(bigramsList.size() - 1));
        for (int i = bigramsList.size() - 2; i >= Math.max(0, bigramsList.size() - 4); i--) {
            intersection.retainAll(bigramsList.get(i));
        }

        return allBigrams.isEmpty() ? 1.0 : 1.0 - ((double) intersection.size() / allBigrams.size());
    }

    /**
     * Retorna os bigramas de um texto
     * @param text Texto
     * @return Bigramas do texto
     */
    private Set<String> getBigrams(String text) {
        Set<String> bigrams = new HashSet<>();
        String[] words = text.toLowerCase().split("\\s+");
        for (int i = 0; i < words.length - 1; i++) {
            if (!STOP_WORDS.contains(words[i]) && !STOP_WORDS.contains(words[i + 1])) {
                bigrams.add(words[i] + " " + words[i + 1]);
            }
        }
        return bigrams;
    }
}
