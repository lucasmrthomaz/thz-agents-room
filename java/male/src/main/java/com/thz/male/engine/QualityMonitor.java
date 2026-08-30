package com.thz.male.engine;

import java.util.*;

/**
 * Monitora a qualidade dos argumentos e injeta feedback nos agentes.
 */
public class QualityMonitor {

    /**
     * Injeta feedback de qualidade na instrução do agente
     * @param health Saúde do debate
     * @param agentRole Papel do agente
     * @param instruction Instrução original
     * @return Instrução com feedback de qualidade
     */
    public String injectQualityFeedback(Map<String, Object> health, String agentRole, String instruction) {
        double diversity = (double) health.getOrDefault("diversityScore", 1.0);
        int repetitionCount = (int) health.getOrDefault("repetitionCount", 0);

        if (repetitionCount >= 2) {
            instruction += "\n\nQUALIDADE: O debate esta com repeticao. " +
                    "Traga dados CONCRETOS da sua area de expertise. " +
                    "Use numeros, metricas, ferramentas especificas.";
        }

        if (diversity < 0.5) {
            instruction += "\n\nDIVERSIDADE: Aborde um ASPECTO DIFERENTE do problema. " +
                    "Nao repita argumentos ja apresentados.";
        }

        return instruction;
    }

    /**
     * Monitora a qualidade de um argumento
     * @param argument Argumento a ser monitorado
     * @param history Histórico da conversa
     * @param agentRole Papel do agente
     * @return Mapa com métricas de qualidade
     */
    public Map<String, Object> monitorArgumentQuality(String argument, List<Map<String, Object>> history,
            String agentRole) {
        Map<String, Object> result = new HashMap<>();
        int wordCount = argument.split("\\s+").length;
        result.put("wordCount", wordCount);
        result.put("isTooShort", wordCount < 20);

        double noveltyScore = calculateNovelty(argument, history);
        result.put("noveltyScore", noveltyScore);

        double expertiseAlignment = calculateExpertiseAlignment(argument, agentRole);
        result.put("expertiseAlignment", expertiseAlignment);

        double overallScore = noveltyScore * 0.4 + expertiseAlignment * 0.3 + Math.min(1.0, wordCount / 100.0) * 0.3;
        result.put("overallScore", overallScore);

        return result;
    }

    /**
     * Calcula a novidade de um argumento
     * @param argument Argumento a ser analisado
     * @param history Histórico da conversa
     * @return Score de novidade
     */
    private double calculateNovelty(String argument, List<Map<String, Object>> history) {
        if (history.size() < 3)
            return 0.8;

        Set<String> argWords = new HashSet<>(Set.of(argument.toLowerCase().split("\\s+")));
        double totalOverlap = 0;

        for (Map<String, Object> h : history) {
            String prev = ((String) h.getOrDefault("content", "")).toLowerCase();
            Set<String> prevWords = new HashSet<>(Set.of(prev.split("\\s+")));
            Set<String> intersection = new HashSet<>(argWords);
            intersection.retainAll(prevWords);
            if (!prevWords.isEmpty()) {
                totalOverlap += (double) intersection.size() / prevWords.size();
            }
        }

        double avgOverlap = totalOverlap / history.size();
        return Math.max(0, Math.min(1, 1.0 - avgOverlap));
    }

    /**
     * Calcula o alinhamento do argumento com a expertise do agente
     * @param argument Argumento a ser analisado
     * @param agentRole Papel do agente
     * @return Score de alinhamento com a expertise
     */
    private double calculateExpertiseAlignment(String argument, String agentRole) {
        Map<String, List<String>> expertiseIndicators = Map.of(
                "Software Architect", List.of("arquitetura", "design", "escala", "monolito", "microservico"),
                "Site Reliability Engineer", List.of("sla", "disponibilidade", "monitoramento", "falha"),
                "DevOps Engineer", List.of("ci/cd", "pipeline", "deploy", "docker", "kubernetes"),
                "Database Specialist", List.of("query", "index", "sql", "banco", "performance"),
                "Security Specialist", List.of("seguranca", "vulnerabilidade", "jwt", "oauth"),
                "Product Owner", List.of("roi", "valor", "usuario", "prioridade"),
                "Scrum Master", List.of("sprint", "processo", "impedimento"),
                "Project Manager", List.of("prazo", "recurso", "risco", "orcamento"),
                "Senior Developer", List.of("codigo", "testes", "solid", "refactor"));

        List<String> indicators = expertiseIndicators.getOrDefault(agentRole, List.of());
        if (indicators.isEmpty())
            return 0.5;

        String argLower = argument.toLowerCase();
        long matchCount = indicators.stream().filter(argLower::contains).count();
        return Math.min(1.0, 0.3 + (double) matchCount / indicators.size() * 0.7);
    }
}
