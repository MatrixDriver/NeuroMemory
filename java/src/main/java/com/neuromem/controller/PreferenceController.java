package com.neuromem.controller;

import com.neuromem.model.dto.PreferenceResponse;
import com.neuromem.model.dto.PreferenceSetRequest;
import com.neuromem.service.PreferenceService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.Map;
import java.util.UUID;

/**
 * Controller for preference management.
 */
@RestController
@RequestMapping("/v1/preferences")
@RequiredArgsConstructor
public class PreferenceController {

    private final PreferenceService preferenceService;

    @PostMapping
    public Mono<PreferenceResponse> setPreference(
            @AuthenticationPrincipal UUID tenantId,
            @Valid @RequestBody PreferenceSetRequest request) {
        return preferenceService.setPreference(tenantId, request);
    }

    @GetMapping
    public Flux<PreferenceResponse> listPreferences(
            @AuthenticationPrincipal UUID tenantId,
            @RequestParam String userId) {
        return preferenceService.listPreferences(tenantId, userId);
    }

    @GetMapping("/{key}")
    public Mono<PreferenceResponse> getPreference(
            @AuthenticationPrincipal UUID tenantId,
            @RequestParam String userId,
            @PathVariable String key) {
        return preferenceService.getPreference(tenantId, userId, key);
    }

    @DeleteMapping("/{key}")
    public Mono<Map<String, Boolean>> deletePreference(
            @AuthenticationPrincipal UUID tenantId,
            @RequestParam String userId,
            @PathVariable String key) {
        return preferenceService.deletePreference(tenantId, userId, key)
                .thenReturn(Map.of("deleted", true));
    }
}
