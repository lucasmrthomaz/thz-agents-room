package com.thz.male.agent;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.*;

public class AgentSoul {

    private final String agentName;
    private final Path soulDir;
    private final Path soulPath;
    private final Path metaPath;

    public AgentSoul(String agentName, Path dataDir) {
        this.agentName = agentName;
        this.soulDir = dataDir.resolve("souls");
        this.soulPath = soulDir.resolve(agentName.toLowerCase().replace(" ", "_") + ".md");
        this.metaPath = soulDir.resolve(agentName.toLowerCase().replace(" ", "_") + ".json");
        init();
    }

    private void init() {
        try {
            Files.createDirectories(soulDir);
        } catch (IOException e) {
            throw new RuntimeException("Failed to create soul directory", e);
        }
    }

    public boolean exists() {
        return Files.exists(soulPath);
    }

    public String load() {
        if (!Files.exists(soulPath))
            return "";
        try {
            return Files.readString(soulPath, StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "";
        }
    }

    public void save(String soulContent) {
        try {
            Files.writeString(soulPath, soulContent, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("Failed to save soul", e);
        }
    }

    public Map<String, Object> loadMeta() {
        if (!Files.exists(metaPath)) {
            return Map.of("version", 0, "lastUpdated", (Object) null, "traits", List.of());
        }
        try {
            String json = Files.readString(metaPath, StandardCharsets.UTF_8);
            return parseSimpleJson(json);
        } catch (IOException e) {
            return Map.of("version", 0, "lastUpdated", (Object) null, "traits", List.of());
        }
    }

    public void saveMeta(Map<String, Object> meta) {
        try {
            String json = toJson(meta);
            Files.writeString(metaPath, json, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new RuntimeException("Failed to save soul meta", e);
        }
    }

    public void addTrait(String trait, String evidence) {
        Map<String, Object> meta = loadMeta();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> traits = (List<Map<String, Object>>) meta.getOrDefault("traits", new ArrayList<>());

        Optional<Map<String, Object>> existing = traits.stream()
                .filter(t -> trait.equals(t.get("trait")))
                .findFirst();

        if (existing.isPresent()) {
            Map<String, Object> t = existing.get();
            @SuppressWarnings("unchecked")
            List<String> evidenceList = (List<String>) t.get("evidence");
            evidenceList.add(evidence);
            t.put("count", ((int) t.getOrDefault("count", 1)) + 1);
            t.put("lastSeen", LocalDateTime.now().toString());
        } else {
            Map<String, Object> newTrait = new LinkedHashMap<>();
            newTrait.put("trait", trait);
            newTrait.put("evidence", List.of(evidence));
            newTrait.put("count", 1);
            newTrait.put("created", LocalDateTime.now().toString());
            newTrait.put("lastSeen", LocalDateTime.now().toString());
            traits.add(newTrait);
        }

        meta.put("traits", traits);
        meta.put("version", (int) meta.getOrDefault("version", 0) + 1);
        meta.put("lastUpdated", LocalDateTime.now().toString());
        saveMeta(meta);
        rebuildSoul(traits);
    }

    public String getPersonalitySummary() {
        Map<String, Object> meta = loadMeta();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> traits = (List<Map<String, Object>>) meta.getOrDefault("traits", List.of());
        if (traits.isEmpty())
            return "";

        traits.sort((a, b) -> (int) b.getOrDefault("count", 0) - (int) a.getOrDefault("count", 0));
        List<Map<String, Object>> topTraits = traits.subList(0, Math.min(5, traits.size()));

        StringBuilder sb = new StringBuilder("Identidade acumulada de debates anteriores:\n");
        for (Map<String, Object> t : topTraits) {
            sb.append("- ").append(t.get("trait"))
                    .append(" (observado ").append(t.getOrDefault("count", 1)).append("x)\n");
        }
        return sb.toString();
    }

    private void rebuildSoul(List<Map<String, Object>> traits) {
        StringBuilder sb = new StringBuilder();
        sb.append("# Soul: ").append(agentName).append("\n\n## Identidade\n\n");

        List<Map<String, Object>> strong = traits.stream()
                .filter(t -> (int) t.getOrDefault("count", 0) >= 3)
                .toList();
        List<Map<String, Object>> moderate = traits.stream()
                .filter(t -> (int) t.getOrDefault("count", 0) < 3 && (int) t.getOrDefault("count", 0) >= 1)
                .toList();

        if (!strong.isEmpty()) {
            sb.append("### Traços Fortes\n");
            for (Map<String, Object> t : strong) {
                sb.append("- **").append(t.get("trait")).append("** (observado ")
                        .append(t.get("count")).append("x)\n");
                @SuppressWarnings("unchecked")
                List<String> evidence = (List<String>) t.get("evidence");
                if (evidence != null && !evidence.isEmpty()) {
                    sb.append("  - Exemplo: ").append(evidence.get(evidence.size() - 1), 0,
                            Math.min(100, evidence.get(evidence.size() - 1).length())).append("\n");
                }
            }
            sb.append("\n");
        }

        if (!moderate.isEmpty()) {
            sb.append("### Traços Emergentes\n");
            for (Map<String, Object> t : moderate) {
                sb.append("- ").append(t.get("trait")).append(" (observado ")
                        .append(t.get("count")).append("x)\n");
            }
            sb.append("\n");
        }

        sb.append("---\n").append("Última atualização: ").append(LocalDateTime.now());
        save(sb.toString());
    }

    private Map<String, Object> parseSimpleJson(String json) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("version", 0);
        map.put("lastUpdated", null);
        map.put("traits", new ArrayList<>());
        return map;
    }

    private String toJson(Map<String, Object> meta) {
        StringBuilder sb = new StringBuilder("{");
        sb.append("\"version\":").append(meta.getOrDefault("version", 0));
        sb.append(",\"lastUpdated\":")
                .append(meta.get("lastUpdated") == null ? "null" : "\"" + meta.get("lastUpdated") + "\"");
        sb.append(",\"traits\":[]}");
        return sb.toString();
    }
}
