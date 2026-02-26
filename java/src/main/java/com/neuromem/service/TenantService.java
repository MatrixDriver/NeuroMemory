package com.neuromem.service;

import com.neuromem.exception.DuplicateResourceException;
import com.neuromem.model.dto.TenantRegisterRequest;
import com.neuromem.model.dto.TenantRegisterResponse;
import com.neuromem.model.entity.ApiKey;
import com.neuromem.model.entity.Tenant;
import com.neuromem.repository.ApiKeyRepository;
import com.neuromem.repository.TenantRepository;
import com.neuromem.util.ApiKeyUtil;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

import java.time.LocalDateTime;
import java.util.UUID;

/**
 * Service for tenant management and registration.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantService {

    private final TenantRepository tenantRepository;
    private final ApiKeyRepository apiKeyRepository;

    /**
     * Register a new tenant and generate API key.
     *
     * @param request Tenant registration request
     * @return Tenant registration response with API key
     */
    @Transactional
    public Mono<TenantRegisterResponse> registerTenant(TenantRegisterRequest request) {
        return tenantRepository.existsByEmail(request.getEmail())
                .flatMap(exists -> {
                    if (exists) {
                        return Mono.error(new DuplicateResourceException("Tenant", request.getEmail()));
                    }

                    // Generate API key
                    String apiKey = ApiKeyUtil.generateApiKey();
                    String keyHash = ApiKeyUtil.hashApiKey(apiKey);
                    String keyPrefix = ApiKeyUtil.getKeyPrefix(apiKey);

                    // Create tenant
                    Tenant tenant = Tenant.builder()
                            .name(request.getName())
                            .email(request.getEmail())
                            .createdAt(LocalDateTime.now())
                            .updatedAt(LocalDateTime.now())
                            .build();

                    return tenantRepository.save(tenant)
                            .flatMap(savedTenant -> {
                                // Create API key
                                ApiKey key = ApiKey.builder()
                                        .tenantId(savedTenant.getId())
                                        .keyHash(keyHash)
                                        .keyPrefix(keyPrefix)
                                        .createdAt(LocalDateTime.now())
                                        .build();

                                return apiKeyRepository.save(key)
                                        .map(savedKey -> TenantRegisterResponse.builder()
                                                .tenantId(savedTenant.getId().toString())
                                                .apiKey(apiKey)
                                                .message("Tenant registered successfully. Save your API key securely!")
                                                .build());
                            });
                });
    }

    /**
     * Verify API key and return tenant ID.
     *
     * @param apiKey The API key to verify
     * @return Tenant UUID if valid
     */
    public Mono<UUID> verifyApiKey(String apiKey) {
        String keyHash = ApiKeyUtil.hashApiKey(apiKey);
        return apiKeyRepository.findByKeyHash(keyHash)
                .flatMap(key -> {
                    // Update last used timestamp
                    apiKeyRepository.updateLastUsed(key.getId()).subscribe();
                    return Mono.just(key.getTenantId());
                })
                .switchIfEmpty(Mono.error(new RuntimeException("Invalid API key")));
    }
}
