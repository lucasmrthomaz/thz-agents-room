package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.thz.male.model.DebateState;

import java.util.List;

@Repository
public interface DebateStateRepository extends JpaRepository<DebateState, String> {

    List<DebateState> findByStatus(String status);

    List<DebateState> findBySessionIdOrderByCurrentTurnDesc(String sessionId);
}
