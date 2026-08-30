package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import com.thz.male.model.Conversation;

import java.util.List;

@Repository
public interface ConversationRepository extends JpaRepository<Conversation, String> {

    List<Conversation> findBySessionIdOrderByCreatedAtDesc(String sessionId);

    @Query(value = "SELECT c.* FROM conversations c " +
            "LEFT JOIN messages m ON m.conversation_id = c.id " +
            "GROUP BY c.id ORDER BY c.created_at DESC LIMIT :limit", nativeQuery = true)
    List<Conversation> findRecentDebates(@Param("limit") int limit);

    @Query(value = "SELECT topic FROM topic_memory ORDER BY last_discussed_at DESC LIMIT :limit", nativeQuery = true)
    List<String> findDiscussedTopics(@Param("limit") int limit);
}
