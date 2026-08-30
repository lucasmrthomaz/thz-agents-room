package com.thz.male.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "topic_memory")
public class TopicMemory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String topic;

    private String category;

    @Column(name = "times_discussed")
    private Integer timesDiscussed = 1;

    @Column(name = "last_consensus")
    private Boolean lastConsensus;

    @Column(name = "last_discussed_at")
    private LocalDateTime lastDiscussedAt;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
        lastDiscussedAt = LocalDateTime.now();
    }

    public TopicMemory() {
    }

    public TopicMemory(String topic, Boolean lastConsensus) {
        this.topic = topic;
        this.lastConsensus = lastConsensus;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTopic() {
        return topic;
    }

    public void setTopic(String topic) {
        this.topic = topic;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public Integer getTimesDiscussed() {
        return timesDiscussed;
    }

    public void setTimesDiscussed(Integer timesDiscussed) {
        this.timesDiscussed = timesDiscussed;
    }

    public Boolean getLastConsensus() {
        return lastConsensus;
    }

    public void setLastConsensus(Boolean lastConsensus) {
        this.lastConsensus = lastConsensus;
    }

    public LocalDateTime getLastDiscussedAt() {
        return lastDiscussedAt;
    }

    public void setLastDiscussedAt(LocalDateTime lastDiscussedAt) {
        this.lastDiscussedAt = lastDiscussedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
