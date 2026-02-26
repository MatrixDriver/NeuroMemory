package com.neuromem.model.entity;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * API Key entity for tenant authentication.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("api_keys")
public class ApiKey {

    @Id
    private UUID id;

    @Column("tenant_id")
    private UUID tenantId;

    @Column("key_hash")
    private String keyHash;

    @Column("key_prefix")
    private String keyPrefix;

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("last_used_at")
    private LocalDateTime lastUsedAt;
}
