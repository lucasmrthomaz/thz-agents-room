package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.thz.male.model.ArgumentScore;

import java.util.List;

@Repository
public interface ArgumentScoreRepository extends JpaRepository<ArgumentScore, Long> {

    List<ArgumentScore> findByConversationId(String conversationId);

    List<ArgumentScore> findByAgentName(String agentName);
}
