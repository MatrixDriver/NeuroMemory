package com.neuromem.repository;

import com.neuromem.model.entity.ApiKey;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * Repository for API Key entities.
 */
@Repository
public interface ApiKeyRepository extends ReactiveCrudRepository<ApiKey, UUID> {

    /**
     * Find API key by key hash.
     */
    Mono<ApiKey> findByKeyHash(String keyHash);

    /**
     * Find API key by key prefix (for lookup optimization).
     */
    @Query("SELECT * FROM api_keys WHERE key_hash = :keyHash")
    Mono<ApiKey> findByKeyHashWithTenant(String keyHash);

    /**
     * Update last used timestamp.
     */
    @Query("UPDATE api_keys SET last_used_at = NOW() WHERE id = :id")
    Mono<Void> updateLastUsed(UUID id);
}
