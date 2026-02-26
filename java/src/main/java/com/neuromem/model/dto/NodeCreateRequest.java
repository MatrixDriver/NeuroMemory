package com.neuromem.model.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * Request DTO for creating a graph node.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class NodeCreateRequest {

    @NotBlank(message = "Node type is required")
    private String nodeType;

    @NotBlank(message = "Node ID is required")
    private String nodeId;

    private Map<String, Object> properties;
}
