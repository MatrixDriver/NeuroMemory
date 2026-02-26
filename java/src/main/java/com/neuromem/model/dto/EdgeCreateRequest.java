package com.neuromem.model.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * Request DTO for creating a graph edge.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class EdgeCreateRequest {

    @NotBlank(message = "Source type is required")
    private String sourceType;

    @NotBlank(message = "Source ID is required")
    private String sourceId;

    @NotBlank(message = "Edge type is required")
    private String edgeType;

    @NotBlank(message = "Target type is required")
    private String targetType;

    @NotBlank(message = "Target ID is required")
    private String targetId;

    private Map<String, Object> properties;
}
