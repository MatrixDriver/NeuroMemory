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
 * Embedding entity for storing memory vectors.
 * Note: R2DBC doesn't support pgvector type directly,
 * so we'll handle vector operations via raw SQL.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("embeddings")
public class Embedding {

    @Id
    private UUID id;

    @Column("tenant_id")
    private UUID tenantId;

    @Column("user_id")
    private String userId;

    @Column("content")
    private String content;

    @Column("memory_type")
    private String memoryType;

    // Vector stored as float array, will be converted to pgvector
    @Column("embedding")
    private float[] embedding;

    @Column("metadata")
    private String metadata; // JSON string

    @Column("created_at")
    private LocalDateTime createdAt;
}
