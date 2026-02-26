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
 * Preference entity for storing user key-value preferences.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("preferences")
public class Preference {

    @Id
    private UUID id;

    @Column("tenant_id")
    private UUID tenantId;

    @Column("user_id")
    private String userId;

    @Column("key")
    private String key;

    @Column("value")
    private String value;

    @Column("metadata")
    private String metadata; // Stored as JSONB, will be String in R2DBC

    @Column("created_at")
    private LocalDateTime createdAt;

    @Column("updated_at")
    private LocalDateTime updatedAt;
}
