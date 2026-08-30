package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

import com.thz.male.model.TopicMemory;

import java.util.List;
import java.util.Optional;

@Repository
public interface TopicMemoryRepository extends JpaRepository<TopicMemory, Long> {

    /**
     * Busca um tópico por nome
     * @param topic Nome do tópico
     * @return Tópico encontrado
     */
    Optional<TopicMemory> findByTopic(String topic);

    /**
     * Busca os tópicos mais recentes
     * @param limit Limite de tópicos a serem buscados
     * @return Lista de tópicos mais recentes
     */
    @Query(value = "SELECT topic FROM topic_memory ORDER BY last_discussed_at DESC LIMIT :limit", nativeQuery = true)
    List<String> findRecentTopics(@Param("limit") int limit);
    
    /**
     * Insere ou atualiza um tópico
     * @param topic Tópico a ser inserido ou atualizado
     * @param consensus Status do tópico
     */
    @Modifying
    @Transactional
    @Query(value = "INSERT INTO topic_memory (topic, last_consensus, last_discussed_at) " +
            "VALUES (:topic, :consensus, CURRENT_TIMESTAMP) " +
            "ON CONFLICT(topic) DO UPDATE SET " +
            "times_discussed = times_discussed + 1, " +
            "last_consensus = :consensus, " +
            "last_discussed_at = CURRENT_TIMESTAMP", nativeQuery = true)
    void upsertTopicMemory(@Param("topic") String topic, @Param("consensus") boolean consensus);
}
