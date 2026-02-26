package com.neuromem.model.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * Request DTO for adding a memory.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MemoryAddRequest {

    @NotBlank(message = "User ID is required")
    private String userId;

    @NotBlank(message = "Content is required")
    private String content;

    @Builder.Default
    private String memoryType = "general";

    private Map<String, Object> metadata;
}
