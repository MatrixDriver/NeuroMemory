package com.neuromem.controller;

import com.neuromem.model.dto.TenantRegisterRequest;
import com.neuromem.model.dto.TenantRegisterResponse;
import com.neuromem.service.TenantService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

/**
 * Controller for tenant registration and management.
 */
@RestController
@RequestMapping("/v1/tenants")
@RequiredArgsConstructor
public class TenantController {

    private final TenantService tenantService;

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<TenantRegisterResponse> registerTenant(@Valid @RequestBody TenantRegisterRequest request) {
        return tenantService.registerTenant(request);
    }
}
