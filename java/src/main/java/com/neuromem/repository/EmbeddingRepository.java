package com.neuromem.repository;

import com.neuromem.model.entity.Embedding;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * Repository for Embedding entities.
 *
 * Note: Vector similarity search requires custom SQL queries
 * since R2DBC doesn't natively support pgvector operations.
 */
@Repository
public interface EmbeddingRepository extends ReactiveCrudRepository<Embedding, UUID> {

    /**
     * Find all embeddings for a user.
     */
    Flux<Embedding> findByTenantIdAndUserId(UUID tenantId, String userId);

    /**
     * Find embeddings by memory type.
     */
    Flux<Embedding> findByTenantIdAndUserIdAndMemoryType(UUID tenantId, String userId, String memoryType);

    /**
     * Count embeddings for a user.
     */
    Mono<Long> countByTenantIdAndUserId(UUID tenantId, String userId);

    /**
     * Vector similarity search.
     * This uses pgvector's <-> operator for cosine distance.
     * The query will be implemented in the service layer using DatabaseClient
     * because R2DBC repository methods don't support custom vector operations.
     */
}
