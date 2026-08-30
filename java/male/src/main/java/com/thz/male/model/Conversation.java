package com.thz.male.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "conversations")
public class Conversation {

    @Id
    @Column(length = 36)
    private String id;

    @Column(nullable = false)
    private String topic;

    @Column(name = "session_id")
    private String sessionId;

    @Column(name = "summary_short")
    private String summaryShort;

    @Column(name = "summary_full")
    private String summaryFull;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public Conversation() {
    }

    public Conversation(String id, String topic, String sessionId) {
        this.id = id;
        this.topic = topic;
        this.sessionId = sessionId;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getTopic() {
        return topic;
    }

    public void setTopic(String topic) {
        this.topic = topic;
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getSummaryShort() {
        return summaryShort;
    }

    public void setSummaryShort(String summaryShort) {
        this.summaryShort = summaryShort;
    }

    public String getSummaryFull() {
        return summaryFull;
    }

    public void setSummaryFull(String summaryFull) {
        this.summaryFull = summaryFull;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
