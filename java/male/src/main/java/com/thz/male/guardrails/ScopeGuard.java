package com.thz.male.guardrails;

import org.springframework.stereotype.Component;

import java.util.*;

@Component
public class ScopeGuard {

    /**
     * Temas permitidos para debate
     */
    private static final Set<String> ALLOWED_THEMES = Set.of(
            "programação", "programacao", "linguagens", "frameworks", "boas práticas", "boas praticas",
            "arquitetura", "software", "monolito", "microserviço", "microservico", "design",
            "git", "controle de versão", "controle de versao", "branching", "merge", "ci",
            "sistemas operacionais", "linux", "windows", "processos", "memória", "memoria",
            "liderança", "lideranca", "gestão", "gestao", "mentoria", "decisão", "decisao",
            "problemas humano-computador", "ux", "produtividade", "automação", "automacao",
            "devops", "infraestrutura", "containers", "cloud", "monitoramento",
            "banco de dados", "bancos de dados", "sql", "nosql", "modelagem", "performance",
            "segurança", "seguranca", "vulnerabilidades", "autenticação", "autenticacao",
            "docker", "kubernetes", "ci/ccd", "pipeline", "deploy",
            "sre", "tolerância", "tolerancia", "falha", "resiliência", "resiliencia",
            "dba", "query", "índice", "indice",
            "scrum", "sprint", "backlog", "story point");
    
    /**
     * Valida se um tópico está dentro do escopo permitido
     * @param topic Tópico a ser validado
     * @return true se o tópico estiver dentro do escopo permitido, false caso contrário
     */
    public ScopeValidation validateTopic(String topic) {
        if (topic == null || topic.isBlank()) {
            return new ScopeValidation(false, "Tópico não pode ser vazio");
        }

        String normalized = topic.toLowerCase().strip();

        for (String theme : ALLOWED_THEMES) {
            if (normalized.contains(theme)) {
                return new ScopeValidation(true, null);
            }
        }
        // Verifica se o tópico contém pelo menos 2 palavras do escopo permitido
        Set<String> words = new HashSet<>(Set.of(normalized.split("\\s+")));
        long matchCount = ALLOWED_THEMES.stream()
                .filter(t -> words.stream().anyMatch(w -> w.contains(t) || t.contains(w)))
                .count();

        if (matchCount >= 2) {
            return new ScopeValidation(true, null);
        }

        return new ScopeValidation(false,
                "Tópico fora do escopo permitido. Temas: programação, arquitetura, git, " +
                        "sistemas operacionais, liderança, UX, DevOps, banco de dados, segurança.");
    }

    /**
     * Representa uma validação de escopo
     * @param allowed true se o tópico estiver dentro do escopo permitido, false caso contrário
     * @param reason Motivo pelo qual o tópico não está dentro do escopo permitido
     */
    public record ScopeValidation(boolean allowed, String reason) {

    }
}
