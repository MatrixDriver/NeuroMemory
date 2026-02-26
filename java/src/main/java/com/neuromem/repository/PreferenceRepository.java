package com.neuromem.repository;

import com.neuromem.model.entity.Preference;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * Repository for Preference entities.
 */
@Repository
public interface PreferenceRepository extends ReactiveCrudRepository<Preference, UUID> {

    /**
     * Find preference by tenant, user, and key.
     */
    Mono<Preference> findByTenantIdAndUserIdAndKey(UUID tenantId, String userId, String key);

    /**
     * Find all preferences for a user in a tenant.
     */
    Flux<Preference> findByTenantIdAndUserId(UUID tenantId, String userId);

    /**
     * Delete preference by tenant, user, and key.
     */
    @Query("DELETE FROM preferences WHERE tenant_id = :tenantId AND user_id = :userId AND key = :key")
    Mono<Void> deleteByTenantIdAndUserIdAndKey(UUID tenantId, String userId, String key);

    /**
     * Count preferences for a user.
     */
    Mono<Long> countByTenantIdAndUserId(UUID tenantId, String userId);
}
