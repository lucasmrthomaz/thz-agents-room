package com.thz.male.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.thz.male.repository.ConversationRepository;
import com.thz.male.repository.MessageRepository;
import com.thz.male.repository.TopicMemoryRepository;

import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Service
public class SessionService {

    @Value("${male.session.duration-hours:8.0}")
    private double durationHours;

    @Value("${male.debate.pause-between-seconds:300}")
    private int pauseBetweenSeconds;

    private final ConversationRepository conversationRepo;
    private final MessageRepository messageRepo;
    private final TopicMemoryRepository topicMemoryRepo;

    /**
     * Construtor do SessionService
     * @param conversationRepo Repositório de conversas
     * @param messageRepo Repositório de mensagens
     * @param topicMemoryRepo Repositório de memória de tópicos
     */
    public SessionService(
            ConversationRepository conversationRepo,
            MessageRepository messageRepo,
            TopicMemoryRepository topicMemoryRepo) {
        this.conversationRepo = conversationRepo;
        this.messageRepo = messageRepo;
        this.topicMemoryRepo = topicMemoryRepo;
    }
    
    /**
     * Obtém o diretório da sessão
     * @param sessionId ID da sessão
     * @return Diretório da sessão
     */
    public Path getSessionDir(String sessionId) {
        LocalDateTime now = LocalDateTime.now();
        Path base = Path.of("sessions");
        Path sessionDir = base.resolve(now.format(DateTimeFormatter.ofPattern("yyyy-MM-dd")))
                .resolve(now.format(DateTimeFormatter.ofPattern("HH-mm")))
                .resolve(sessionId);
        try {
            Files.createDirectories(sessionDir);
        } catch (Exception e) {
            throw new RuntimeException("Failed to create session directory", e);
        }
        return sessionDir;
    }

    /**
     * Salva o resumo da sessão
     * @param sessionId ID da sessão
     * @param data Dados do resumo
     */
    public void saveSessionSummary(String sessionId, Map<String, Object> data) {
        Path sessionDir = getSessionDir(sessionId);
        try {
            String json = toJson(data);
            Files.writeString(sessionDir.resolve("nightly_summary.json"), json,
                    StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new RuntimeException("Failed to save session summary", e);
        }
    }

    /**
     * Converte um mapa em JSON
     * @param data Mapa a ser convertido
     * @return JSON convertido
     */
    private String toJson(Map<String, Object> data) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            if (!first)
                sb.append(",");
            first = false;
            sb.append("\"").append(entry.getKey()).append("\":");
            Object value = entry.getValue();
            if (value == null) {
                sb.append("null");
            } else if (value instanceof Number || value instanceof Boolean) {
                sb.append(value);
            } else {
                sb.append("\"").append(value.toString().replace("\"", "\\\"")).append("\"");
            }
        }
        sb.append("}");
        return sb.toString();
    }
}
