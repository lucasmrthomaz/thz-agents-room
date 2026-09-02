package com.thz.male.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.thz.male.service.DebateService;
import com.thz.male.service.ModelService;
import com.thz.male.service.TopicService;

import java.util.*;

/**
 * API REST para debaters
 * - /api/models
 * - /api/debates
 * - /api/debates/{conversationId}/messages
 * - /api/topics/{topic}/history
 */
@RestController
@RequestMapping("/api")
public class RestApiController {

    private final DebateService debateService;
    private final ModelService modelService;
    private final TopicService topicService;

    public RestApiController(DebateService debateService, ModelService modelService, TopicService topicService) {
        this.debateService = debateService;
        this.modelService = modelService;
        this.topicService = topicService;
    }

    @GetMapping("/models")
    public ResponseEntity<Map<String, Object>> listModels() {
        List<String> models = modelService.listAvailableModels();
        return ResponseEntity.ok(Map.of("models", models));
    }

    @GetMapping("/debates")
    public ResponseEntity<Map<String, Object>> listDebates(
            @RequestParam(defaultValue = "20") int limit) {
        List<Map<String, Object>> debates = debateService.getRecentDebates(limit);
        return ResponseEntity.ok(Map.of("debates", debates, "total", debates.size()));
    }

    @GetMapping("/debates/{conversationId}/messages")
    public ResponseEntity<Map<String, Object>> getDebateMessages(
            @PathVariable String conversationId) {
        List<Map<String, Object>> messages = debateService.getDebateMessages(conversationId);
        return ResponseEntity.ok(Map.of("messages", messages));
    }

    @GetMapping("/topics/{topic}/history")
    public ResponseEntity<Map<String, Object>> getTopicHistory(@PathVariable String topic) {
        Map<String, Object> history = debateService.getTopicHistory(topic);
        return ResponseEntity.ok(history != null ? history : Map.of("message", "Topic not found"));
    }

    @GetMapping("/scenario")
    public ResponseEntity<Map<String, Object>> generateScenario() {
        String model = modelService.resolveModel("auto");
        String topic = topicService.generateTopic(model, List.of());
        return ResponseEntity.ok(Map.of("topic", topic));
    }
}
