package com.neuromem.repository;

import com.neuromem.model.entity.Tenant;
import org.springframework.data.r2dbc.repository.Query;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

import java.util.UUID;

/**
 * Repository for Tenant entities.
 */
@Repository
public interface TenantRepository extends ReactiveCrudRepository<Tenant, UUID> {

    /**
     * Find tenant by email.
     */
    Mono<Tenant> findByEmail(String email);

    /**
     * Check if email exists.
     */
    @Query("SELECT EXISTS(SELECT 1 FROM tenants WHERE email = :email)")
    Mono<Boolean> existsByEmail(String email);
}
