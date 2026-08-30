package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.thz.male.model.AgentSkill;

import java.util.List;

@Repository
public interface AgentSkillRepository extends JpaRepository<AgentSkill, Long> {

    List<AgentSkill> findByAgentNameOrderByExpertiseLevelDesc(String agentName);

    List<AgentSkill> findByAgentName(String agentName);
}
