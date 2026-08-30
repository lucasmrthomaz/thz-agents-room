package com.thz.male.service;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.ollama.api.OllamaOptions;
import org.springframework.stereotype.Service;

import com.thz.male.repository.TopicMemoryRepository;

import java.util.*;

@Service
public class TopicService {

    private final ChatClient chatClient;
    private final TopicMemoryRepository topicMemoryRepo;

    /**
     * Lista de tópicos de fallback caso o modelo não consiga gerar um tópico.
     */
    private static final List<String> FALLBACK_TOPICS = List.of(
            "Microservicos vs Monolito: quando a complexidade nao compensa",
            "Event sourcing: quando vale a pena implementar?",
            "CI/CD com GitHub Actions vs GitLab CI: pros e contras",
            "Docker vs Podman: vale a pena trocar?",
            "PostgreSQL vs MongoDB: quando o NoSQL nao e a resposta",
            "Kafka vs RabbitMQ: qual fila de mensagens escolher?",
            "Seguranca em APIs: OAuth2, JWT e boas praticas",
            "Git flow vs trunk-based development: qual adotar?",
            "Testes unitarios vs integracao: onde parar?",
            "Observabilidade: Grafana + Prometheus ou solucoes gerenciadas?");

    /**
     * Construtor do TopicService
     * @param chatClient Cliente de chat
     * @param topicMemoryRepo Repositório de memória de tópicos
     */
    public TopicService(ChatClient chatClient, TopicMemoryRepository topicMemoryRepo) {
        this.chatClient = chatClient;
        this.topicMemoryRepo = topicMemoryRepo;
    }

    /**
     * Gera um tópico de debate técnico
     * @param model Modelo a ser usado
     * @param recentTopics Tópicos recentes
     * @return Tópico gerado
     */
    public String generateTopic(String model, List<String> recentTopics) {
        String already = recentTopics.isEmpty() ? "Nenhum"
                : String.join("\n", recentTopics.stream().map(t -> "- " + t).toList());

        String prompt = "Sugira UM topico de debate tecnico ORIGINAL e INTERESSANTE para engenheiros de software.\n" +
                "Responda SOMENTE com o topico. Nao explique.\n" +
                "Seja criativo - pense em topicos atuais, controversos, ou comparacoes nao obvias.\n" +
                "IMPORTANTE: Varie a ESTRUTURA do topico.\n" +
                "Topicos ja discutidos (EVITE repetir):\n" + already + "\n\n" +
                "Topico:";

        try {
            String response = chatClient.prompt()
                    .user(prompt)
                    .options(OllamaOptions.builder()
                            .model(model)
                            .temperature(0.9)
                            .build())
                    .call()
                    .content();

            String topic = response.strip().replace("\"", "").replace("'", "");
            if (topic.length() >= 10 && topic.length() <= 150) {
                if (!isTooSimilar(topic, recentTopics)) {
                    return topic;
                }
            }
        } catch (Exception e) {
            // Fallback
        }

        List<String> available = FALLBACK_TOPICS.stream()
                .filter(t -> !isTooSimilar(t, recentTopics))
                .toList();

        if (available.isEmpty())
            return FALLBACK_TOPICS.get(0);
        return available.get(new Random().nextInt(available.size()));
    }

    /**
     * Verifica se um tópico é muito similar a tópicos recentes
     * @param newTopic Tópico a ser verificado
     * @param recentTopics Tópicos recentes
     * @return true se o tópico for muito similar a tópicos recentes, false caso contrário
     */
    private boolean isTooSimilar(String newTopic, List<String> recentTopics) {
        String normalized = newTopic.toLowerCase().strip();
        for (String old : recentTopics) {
            String oldNorm = old.toLowerCase().strip();
            if (normalized.equals(oldNorm))
                return true;

            Set<String> words1 = new HashSet<>(Set.of(normalized.split("\\s+")));
            Set<String> words2 = new HashSet<>(Set.of(oldNorm.split("\\s+")));
            Set<String> intersection = new HashSet<>(words1);
            intersection.retainAll(words2);
            Set<String> union = new HashSet<>(words1);
            union.addAll(words2);
            if (!union.isEmpty() && (double) intersection.size() / union.size() > 0.7) {
                return true;
            }
        }
        return false;
    }
}
