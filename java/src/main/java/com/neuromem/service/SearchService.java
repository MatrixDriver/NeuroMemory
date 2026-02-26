package com.neuromem.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.neuromem.model.dto.*;
import com.neuromem.model.entity.Embedding;
import com.neuromem.repository.EmbeddingRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;

/**
 * Service for memory storage and semantic search.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SearchService {

    private final EmbeddingRepository embeddingRepository;
    private final EmbeddingService embeddingService;
    private final DatabaseClient databaseClient;
    private final ObjectMapper objectMapper;

    /**
     * Add a new memory with automatic embedding generation.
     *
     * @param tenantId Tenant ID
     * @param request Memory add request
     * @return Memory response with ID
     */
    @Transactional
    public Mono<Map<String, String>> addMemory(UUID tenantId, MemoryAddRequest request) {
        return embeddingService.generateEmbedding(request.getContent())
                .flatMap(embedding -> {
                    Embedding entity = Embedding.builder()
                            .tenantId(tenantId)
                            .userId(request.getUserId())
                            .content(request.getContent())
                            .memoryType(request.getMemoryType())
                            .embedding(embedding)
                            .metadata(serializeMetadata(request.getMetadata()))
                            .createdAt(LocalDateTime.now())
                            .build();

                    return embeddingRepository.save(entity)
                            .map(saved -> Map.of(
                                    "id", saved.getId().toString(),
                                    "userId", saved.getUserId(),
                                    "content", saved.getContent(),
                                    "memoryType", saved.getMemoryType()
                            ));
                });
    }

    /**
     * Semantic search for memories.
     *
     * @param tenantId Tenant ID
     * @param request Search request
     * @return Search response with results
     */
    public Mono<SearchResponse> search(UUID tenantId, SearchRequest request) {
        return embeddingService.generateEmbedding(request.getQuery())
                .flatMap(queryEmbedding -> {
                    // Build vector search SQL query
                    // Using pgvector's <-> operator for cosine distance
                    String sql = "SELECT id, user_id, content, memory_type, metadata, " +
                            "embedding <-> $1::vector AS score " +
                            "FROM embeddings " +
                            "WHERE tenant_id = $2 AND user_id = $3";

                    if (request.getMemoryType() != null) {
                        sql += " AND memory_type = $4";
                    }

                    sql += " ORDER BY score ASC LIMIT $" + (request.getMemoryType() != null ? "5" : "4");

                    DatabaseClient.GenericExecuteSpec spec = databaseClient.sql(sql)
                            .bind("$1", formatVector(queryEmbedding))
                            .bind("$2", tenantId)
                            .bind("$3", request.getUserId());

                    if (request.getMemoryType() != null) {
                        spec = spec.bind("$4", request.getMemoryType());
                        spec = spec.bind("$5", request.getLimit());
                    } else {
                        spec = spec.bind("$4", request.getLimit());
                    }

                    return spec.fetch()
                            .all()
                            .map(row -> SearchResult.builder()
                                    .id(row.get("id").toString())
                                    .content((String) row.get("content"))
                                    .memoryType((String) row.get("memory_type"))
                                    .metadata(deserializeMetadata((String) row.get("metadata")))
                                    .score(((Number) row.get("score")).doubleValue())
                                    .build())
                            .collectList()
                            .map(results -> SearchResponse.builder()
                                    .userId(request.getUserId())
                                    .query(request.getQuery())
                                    .results(results)
                                    .build());
                });
    }

    /**
     * Get user memories overview (count).
     *
     * @param tenantId Tenant ID
     * @param userId User ID
     * @return Memory counts
     */
    public Mono<Map<String, Object>> getUserMemoriesOverview(UUID tenantId, String userId) {
        return embeddingRepository.countByTenantIdAndUserId(tenantId, userId)
                .map(count -> Map.of(
                        "userId", userId,
                        "embeddingCount", count,
                        "preferenceCount", 0  // TODO: Add preference count
                ));
    }

    /**
     * Format float array as pgvector string format.
     */
    private String formatVector(float[] vector) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < vector.length; i++) {
            if (i > 0) sb.append(",");
            sb.append(vector[i]);
        }
        sb.append("]");
        return sb.toString();
    }

    private String serializeMetadata(Map<String, Object> metadata) {
        if (metadata == null) return null;
        try {
            return objectMapper.writeValueAsString(metadata);
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize metadata", e);
            return null;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> deserializeMetadata(String metadata) {
        if (metadata == null) return null;
        try {
            return objectMapper.readValue(metadata, Map.class);
        } catch (JsonProcessingException e) {
            log.warn("Failed to deserialize metadata", e);
            return null;
        }
    }
}
