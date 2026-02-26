package com.neuromem.model.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * Request DTO for setting a preference.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class PreferenceSetRequest {

    @NotBlank(message = "User ID is required")
    private String userId;

    @NotBlank(message = "Key is required")
    private String key;

    @NotBlank(message = "Value is required")
    private String value;

    private Map<String, Object> metadata;
}
