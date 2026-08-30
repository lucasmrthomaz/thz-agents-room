package com.thz.male.model;

import jakarta.persistence.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "agent_skills", uniqueConstraints = {
        @UniqueConstraint(columnNames = { "agent_name", "skill_domain" })
})
public class AgentSkill {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "agent_name", nullable = false)
    private String agentName;

    @Column(name = "skill_domain", nullable = false)
    private String skillDomain;

    @Column(name = "expertise_level")
    private Double expertiseLevel = 0.5;

    @Column(name = "times_applied")
    private Integer timesApplied = 0;

    @Column(name = "consensus_contributions")
    private Integer consensusContributions = 0;

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        createdAt = LocalDateTime.now();
    }

    public AgentSkill() {
    }

    public AgentSkill(String agentName, String skillDomain, Double expertiseLevel) {
        this.agentName = agentName;
        this.skillDomain = skillDomain;
        this.expertiseLevel = expertiseLevel;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getAgentName() {
        return agentName;
    }

    public void setAgentName(String agentName) {
        this.agentName = agentName;
    }

    public String getSkillDomain() {
        return skillDomain;
    }

    public void setSkillDomain(String skillDomain) {
        this.skillDomain = skillDomain;
    }

    public Double getExpertiseLevel() {
        return expertiseLevel;
    }

    public void setExpertiseLevel(Double expertiseLevel) {
        this.expertiseLevel = expertiseLevel;
    }

    public Integer getTimesApplied() {
        return timesApplied;
    }

    public void setTimesApplied(Integer timesApplied) {
        this.timesApplied = timesApplied;
    }

    public Integer getConsensusContributions() {
        return consensusContributions;
    }

    public void setConsensusContributions(Integer consensusContributions) {
        this.consensusContributions = consensusContributions;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }
}
