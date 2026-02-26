package com.neuromem.service;

import com.neuromem.exception.DuplicateResourceException;
import com.neuromem.model.dto.TenantRegisterRequest;
import com.neuromem.model.dto.TenantRegisterResponse;
import com.neuromem.model.entity.ApiKey;
import com.neuromem.model.entity.Tenant;
import com.neuromem.repository.ApiKeyRepository;
import com.neuromem.repository.TenantRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

/**
 * Unit tests for TenantService.
 */
@ExtendWith(MockitoExtension.class)
class TenantServiceTest {

    @Mock
    private TenantRepository tenantRepository;

    @Mock
    private ApiKeyRepository apiKeyRepository;

    @InjectMocks
    private TenantService tenantService;

    private TenantRegisterRequest request;
    private Tenant tenant;
    private ApiKey apiKey;

    @BeforeEach
    void setUp() {
        request = TenantRegisterRequest.builder()
                .name("Test Tenant")
                .email("test@example.com")
                .build();

        tenant = Tenant.builder()
                .id(UUID.randomUUID())
                .name("Test Tenant")
                .email("test@example.com")
                .build();

        apiKey = ApiKey.builder()
                .id(UUID.randomUUID())
                .tenantId(tenant.getId())
                .keyHash("hash")
                .keyPrefix("nm_")
                .build();
    }

    @Test
    void registerTenant_Success() {
        when(tenantRepository.existsByEmail(request.getEmail())).thenReturn(Mono.just(false));
        when(tenantRepository.save(any(Tenant.class))).thenReturn(Mono.just(tenant));
        when(apiKeyRepository.save(any(ApiKey.class))).thenReturn(Mono.just(apiKey));

        Mono<TenantRegisterResponse> result = tenantService.registerTenant(request);

        StepVerifier.create(result)
                .expectNextMatches(response ->
                        response.getTenantId().equals(tenant.getId().toString()) &&
                        response.getApiKey().startsWith("nm_"))
                .verifyComplete();
    }

    @Test
    void registerTenant_DuplicateEmail() {
        when(tenantRepository.existsByEmail(request.getEmail())).thenReturn(Mono.just(true));

        Mono<TenantRegisterResponse> result = tenantService.registerTenant(request);

        StepVerifier.create(result)
                .expectError(DuplicateResourceException.class)
                .verify();
    }
}
