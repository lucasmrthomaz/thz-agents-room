package com.thz.male.service;

import org.springframework.stereotype.Service;

import com.thz.male.repository.*;

import java.util.*;

@Service
public class DebateService {

    private final ConversationRepository conversationRepo;
    private final MessageRepository messageRepo;
    private final TopicMemoryRepository topicMemoryRepo;
    private final DebateStateRepository debateStateRepo;

    public DebateService(
            ConversationRepository conversationRepo,
            MessageRepository messageRepo,
            TopicMemoryRepository topicMemoryRepo,
            DebateStateRepository debateStateRepo) {
        this.conversationRepo = conversationRepo;
        this.messageRepo = messageRepo;
        this.topicMemoryRepo = topicMemoryRepo;
        this.debateStateRepo = debateStateRepo;
    }

    public List<Map<String, Object>> getRecentDebates(int limit) {
        var conversations = conversationRepo.findRecentDebates(limit);
        List<Map<String, Object>> result = new ArrayList<>();
        for (var c : conversations) {
            var messages = messageRepo.findByConversationIdOrderByTurnAsc(c.getId());
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("conversationId", c.getId());
            entry.put("topic", c.getTopic());
            entry.put("createdAt", c.getCreatedAt());
            entry.put("messageCount", messages.size());
            result.add(entry);
        }
        return result;
    }

    public List<Map<String, Object>> getDebateMessages(String conversationId) {
        var messages = messageRepo.findByConversationIdOrderByTurnAsc(conversationId);
        List<Map<String, Object>> result = new ArrayList<>();
        for (var m : messages) {
            Map<String, Object> entry = new LinkedHashMap<>();
            entry.put("agentName", m.getAgentName());
            entry.put("content", m.getContent());
            entry.put("status", m.getStatus());
            entry.put("turnNumber", m.getTurn());
            result.add(entry);
        }
        return result;
    }

    public Map<String, Object> getTopicHistory(String topic) {
        return topicMemoryRepo.findByTopic(topic)
                .map(tm -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("topic", tm.getTopic());
                    result.put("timesDiscussed", tm.getTimesDiscussed());
                    result.put("lastConsensus", tm.getLastConsensus());
                    result.put("lastDiscussedAt", tm.getLastDiscussedAt());
                    return result;
                })
                .orElse(null);
    }
}
