package com.thz.male.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "debate_state")
public class DebateState {

    @Id
    @Column(name = "conversation_id", length = 36)
    private String conversationId;

    private String topic;

    @Column(name = "current_turn")
    private Integer currentTurn;

    @Column(name = "history_json", columnDefinition = "TEXT")
    private String historyJson;

    @Column(nullable = false)
    private String status = "active";

    @Column(name = "session_id")
    private String sessionId;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public DebateState() {
    }

    public DebateState(String conversationId, String topic, Integer currentTurn, String historyJson) {
        this.conversationId = conversationId;
        this.topic = topic;
        this.currentTurn = currentTurn;
        this.historyJson = historyJson;
    }

    public String getConversationId() {
        return conversationId;
    }

    public void setConversationId(String conversationId) {
        this.conversationId = conversationId;
    }

    public String getTopic() {
        return topic;
    }

    public void setTopic(String topic) {
        this.topic = topic;
    }

    public Integer getCurrentTurn() {
        return currentTurn;
    }

    public void setCurrentTurn(Integer currentTurn) {
        this.currentTurn = currentTurn;
    }

    public String getHistoryJson() {
        return historyJson;
    }

    public void setHistoryJson(String historyJson) {
        this.historyJson = historyJson;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
