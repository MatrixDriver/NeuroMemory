package com.neuromem.model.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Map;

/**
 * Response DTO for a graph node.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class NodeResponse {
    private String id;
    private String tenantId;
    private String nodeType;
    private String nodeId;
    private Map<String, Object> properties;
    private LocalDateTime createdAt;
}
