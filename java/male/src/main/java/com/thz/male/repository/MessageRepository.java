package com.thz.male.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import com.thz.male.model.Message;

import java.util.List;
import java.util.Optional;

@Repository
public interface MessageRepository extends JpaRepository<Message, Long> {

       List<Message> findByConversationIdOrderByTurnAsc(String conversationId);

       Optional<Message> findByIdempotencyKey(String idempotencyKey);
       
       //
       /**
        * Conta o número de mensagens por agente
        * @return Lista de agentes e o número de mensagens
        */
       @Query(value = "SELECT agent_name, COUNT(*) as total, " +
                     "SUM(CASE WHEN status = 'CONSENSUS' THEN 1 ELSE 0 END) as consensus_count " +
                     "FROM messages GROUP BY agent_name", nativeQuery = true)
       List<Object[]> countByAgentName();

       /**
        * Busca mensagens por palavra-chave
        * @param keyword Palavra-chave
        * @param limit Limite de resultados
        * @return Lista de mensagens por palavra-chave
        */
       @Query(value = "SELECT DISTINCT m.agent_name, m.content, m.status, c.topic, c.created_at " +
                     "FROM messages m JOIN conversations c ON c.id = m.conversation_id " +
                     "WHERE c.topic LIKE %:keyword% ORDER BY c.created_at DESC LIMIT :limit", nativeQuery = true)
       List<Object[]> searchByKeyword(@Param("keyword") String keyword, @Param("limit") int limit);
}
