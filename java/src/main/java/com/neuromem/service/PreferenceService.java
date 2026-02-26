package com.neuromem.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.neuromem.exception.ResourceNotFoundException;
import com.neuromem.model.dto.PreferenceResponse;
import com.neuromem.model.dto.PreferenceSetRequest;
import com.neuromem.model.entity.Preference;
import com.neuromem.repository.PreferenceRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;

/**
 * Service for preference management.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class PreferenceService {

    private final PreferenceRepository preferenceRepository;
    private final ObjectMapper objectMapper;

    /**
     * Set a preference (create or update).
     *
     * @param tenantId Tenant ID
     * @param request Preference set request
     * @return Preference response
     */
    @Transactional
    public Mono<PreferenceResponse> setPreference(UUID tenantId, PreferenceSetRequest request) {
        return preferenceRepository.findByTenantIdAndUserIdAndKey(tenantId, request.getUserId(), request.getKey())
                .flatMap(existing -> {
                    // Update existing preference
                    existing.setValue(request.getValue());
                    existing.setMetadata(serializeMetadata(request.getMetadata()));
                    existing.setUpdatedAt(LocalDateTime.now());
                    return preferenceRepository.save(existing);
                })
                .switchIfEmpty(
                        // Create new preference
                        Mono.defer(() -> {
                            Preference newPref = Preference.builder()
                                    .tenantId(tenantId)
                                    .userId(request.getUserId())
                                    .key(request.getKey())
                                    .value(request.getValue())
                                    .metadata(serializeMetadata(request.getMetadata()))
                                    .createdAt(LocalDateTime.now())
                                    .updatedAt(LocalDateTime.now())
                                    .build();
                            return preferenceRepository.save(newPref);
                        })
                )
                .map(this::toResponse);
    }

    /**
     * Get a specific preference.
     *
     * @param tenantId Tenant ID
     * @param userId User ID
     * @param key Preference key
     * @return Preference response
     */
    public Mono<PreferenceResponse> getPreference(UUID tenantId, String userId, String key) {
        return preferenceRepository.findByTenantIdAndUserIdAndKey(tenantId, userId, key)
                .map(this::toResponse)
                .switchIfEmpty(Mono.error(new ResourceNotFoundException("Preference", key)));
    }

    /**
     * List all preferences for a user.
     *
     * @param tenantId Tenant ID
     * @param userId User ID
     * @return Flux of preferences
     */
    public Flux<PreferenceResponse> listPreferences(UUID tenantId, String userId) {
        return preferenceRepository.findByTenantIdAndUserId(tenantId, userId)
                .map(this::toResponse);
    }

    /**
     * Delete a preference.
     *
     * @param tenantId Tenant ID
     * @param userId User ID
     * @param key Preference key
     * @return Mono<Void>
     */
    @Transactional
    public Mono<Void> deletePreference(UUID tenantId, String userId, String key) {
        return preferenceRepository.findByTenantIdAndUserIdAndKey(tenantId, userId, key)
                .switchIfEmpty(Mono.error(new ResourceNotFoundException("Preference", key)))
                .flatMap(pref -> preferenceRepository.deleteByTenantIdAndUserIdAndKey(tenantId, userId, key));
    }

    /**
     * Convert entity to response DTO.
     */
    private PreferenceResponse toResponse(Preference pref) {
        return PreferenceResponse.builder()
                .userId(pref.getUserId())
                .key(pref.getKey())
                .value(pref.getValue())
                .metadata(deserializeMetadata(pref.getMetadata()))
                .createdAt(pref.getCreatedAt())
                .updatedAt(pref.getUpdatedAt())
                .build();
    }

    /**
     * Serialize metadata map to JSON string.
     */
    private String serializeMetadata(Map<String, Object> metadata) {
        if (metadata == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(metadata);
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize metadata", e);
            return null;
        }
    }

    /**
     * Deserialize JSON string to metadata map.
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> deserializeMetadata(String metadata) {
        if (metadata == null) {
            return null;
        }
        try {
            return objectMapper.readValue(metadata, Map.class);
        } catch (JsonProcessingException e) {
            log.warn("Failed to deserialize metadata", e);
            return null;
        }
    }
}
