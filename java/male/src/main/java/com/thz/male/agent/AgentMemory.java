package com.thz.male.agent;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.*;

/**
 * AgentMemory:
 * -- Armazena memoria episódica do agente -- 
 *  1. topic: tópico debatido
 *  2. outcome: resultado do debate
 *  3. myArgument: argumento usado pelo agente
 *  4. turn: número de turnos
 *  5. consensus: se houve consenso
 * 6. timestamp: data e hora do debate
 */
public class AgentMemory {

    private final Path memoryDir;
    private final Path episodesPath;
    private final List<Map<String, Object>> episodes;

    /**
     * Construtor do AgentMemory
     * @param agentName Nome do agente
     * @param dataDir Diretório raiz dos dados
     */
    public AgentMemory(String agentName, Path dataDir) {
        this.memoryDir = dataDir.resolve("memory");
        this.episodesPath = memoryDir.resolve(agentName.toLowerCase().replace(" ", "_") + "_episodes.json");
        this.episodes = new ArrayList<>();
        init();
    }

    /**
     * Inicializa a memória, criando o diretório de memória e lendo os episódios salvos
     */
    private void init() {
        try {
            Files.createDirectories(memoryDir);
            if (Files.exists(episodesPath)) {
                String content = Files.readString(episodesPath, StandardCharsets.UTF_8);
                episodes.addAll(parseEpisodes(content));
            }
        } catch (IOException e) {
            throw new RuntimeException("Failed to initialize memory", e);
        }
    }

    /**
     * Grava um episódio na memória
     * @param topic Tópico debatido
     * @param outcome Resultado do debate
     * @param myArgument Argumento usado pelo agente
     * @param turn Número de turnos
     * @param consensus Se houve consenso
     */
    public void recordEpisode(String topic, String outcome, String myArgument, int turn, boolean consensus) {
        Map<String, Object> episode = new LinkedHashMap<>();
        episode.put("topic", topic);
        episode.put("outcome", outcome);
        episode.put("myArgument", myArgument);
        episode.put("turn", turn);
        episode.put("consensus", consensus);
        episode.put("timestamp", LocalDateTime.now().toString());
        episodes.add(episode);
        save();
    }

    /**
     * Retorna um resumo semântico da memória
     * @return Resumo semântico da memória
     */
    public String getSemanticSummary() {
        if (episodes.isEmpty())
            return "";

        long consensusCount = episodes.stream()
                .filter(e -> (boolean) e.getOrDefault("consensus", false))
                .count();

        Set<String> topics = new HashSet<>();
        for (Map<String, Object> ep : episodes) {
            topics.add((String) ep.getOrDefault("topic", ""));
        }

        StringBuilder sb = new StringBuilder();
        sb.append("Memoria episodica: ").append(episodes.size()).append(" episodios, ");
        sb.append(consensusCount).append(" com consenso\n");
        sb.append("Topics discutidos: ").append(topics.size());
        if (!topics.isEmpty()) {
            sb.append(" (ultimos 3): ");
            List<String> recentTopics = new ArrayList<>(topics);
            for (int i = 0; i < Math.min(3, recentTopics.size()); i++) {
                sb.append(recentTopics.get(i));
                if (i < Math.min(3, recentTopics.size()) - 1)
                    sb.append(", ");
            }
        }
        return sb.toString();
    }

    /**
     * Salva a memória no arquivo
     */
    private void save() {
        try {
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < episodes.size(); i++) {
                Map<String, Object> ep = episodes.get(i);
                sb.append("{\"topic\":\"").append(escapeJson(ep.get("topic"))).append("\"");
                sb.append(",\"outcome\":\"").append(escapeJson(ep.get("outcome"))).append("\"");
                sb.append(",\"myArgument\":\"").append(escapeJson(ep.get("myArgument"))).append("\"");
                sb.append(",\"turn\":").append(ep.get("turn"));
                sb.append(",\"consensus\":").append(ep.get("consensus"));
                sb.append(",\"timestamp\":\"").append(ep.get("timestamp")).append("\"}");
                if (i < episodes.size() - 1)
                    sb.append(",");
            }
            sb.append("]");
            Files.writeString(episodesPath, sb.toString(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("Failed to save memory", e);
        }
    }

    /**
     * Analisa o JSON de episódios salvos
     * @param json JSON de episódios
     * @return Lista de episódios
     */
    private List<Map<String, Object>> parseEpisodes(String json) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (json == null || json.isBlank())
            return result;
        return result;
    }

    /**
     * Escapa caracteres especiais no JSON
     * @param value Valor a ser escapado
     * @return Valor escapado
     */
    private String escapeJson(Object value) {
        if (value == null)
            return "";
        return value.toString().replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n");
    }
}
