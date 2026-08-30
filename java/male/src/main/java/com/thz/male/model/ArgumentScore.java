package com.thz.male.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "argument_scores")
public class ArgumentScore {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "message_id")
    private String messageId;

    @Column(name = "conversation_id")
    private String conversationId;

    @Column(name = "agent_name")
    private String agentName;

    @Column(name = "quality_score")
    private Double qualityScore;

    @Column(name = "novelty_score")
    private Double noveltyScore;

    @Column(name = "expertise_alignment")
    private Double expertiseAlignment;

    @Column(name = "overall_score")
    private Double overallScore;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public ArgumentScore() {
    }

    public ArgumentScore(String messageId, String conversationId, String agentName,
            Double qualityScore, Double noveltyScore,
            Double expertiseAlignment, Double overallScore) {
        this.messageId = messageId;
        this.conversationId = conversationId;
        this.agentName = agentName;
        this.qualityScore = qualityScore;
        this.noveltyScore = noveltyScore;
        this.expertiseAlignment = expertiseAlignment;
        this.overallScore = overallScore;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getMessageId() {
        return messageId;
    }

    public void setMessageId(String messageId) {
        this.messageId = messageId;
    }

    public String getConversationId() {
        return conversationId;
    }

    public void setConversationId(String conversationId) {
        this.conversationId = conversationId;
    }

    public String getAgentName() {
        return agentName;
    }

    public void setAgentName(String agentName) {
        this.agentName = agentName;
    }

    public Double getQualityScore() {
        return qualityScore;
    }

    public void setQualityScore(Double qualityScore) {
        this.qualityScore = qualityScore;
    }

    public Double getNoveltyScore() {
        return noveltyScore;
    }

    public void setNoveltyScore(Double noveltyScore) {
        this.noveltyScore = noveltyScore;
    }

    public Double getExpertiseAlignment() {
        return expertiseAlignment;
    }

    public void setExpertiseAlignment(Double expertiseAlignment) {
        this.expertiseAlignment = expertiseAlignment;
    }

    public Double getOverallScore() {
        return overallScore;
    }

    public void setOverallScore(Double overallScore) {
        this.overallScore = overallScore;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
