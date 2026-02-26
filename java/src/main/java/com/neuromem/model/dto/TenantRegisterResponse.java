package com.neuromem.model.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Response DTO for tenant registration.
 * Contains the API key which is only returned once at creation.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TenantRegisterResponse {
    private String tenantId;
    private String apiKey;
    private String message;
}
