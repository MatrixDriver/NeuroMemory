package com.neuromem.controller;

import com.neuromem.model.dto.MemoryAddRequest;
import com.neuromem.model.dto.SearchRequest;
import com.neuromem.model.dto.SearchResponse;
import com.neuromem.service.SearchService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

import java.util.Map;
import java.util.UUID;

/**
 * Controller for memory storage and semantic search.
 */
@RestController
@RequestMapping("/v1")
@RequiredArgsConstructor
public class SearchController {

    private final SearchService searchService;

    @PostMapping("/memories")
    public Mono<Map<String, String>> addMemory(
            @AuthenticationPrincipal UUID tenantId,
            @Valid @RequestBody MemoryAddRequest request) {
        return searchService.addMemory(tenantId, request);
    }

    @PostMapping("/search")
    public Mono<SearchResponse> search(
            @AuthenticationPrincipal UUID tenantId,
            @Valid @RequestBody SearchRequest request) {
        return searchService.search(tenantId, request);
    }

    @GetMapping("/users/{userId}/memories")
    public Mono<Map<String, Object>> getUserMemories(
            @AuthenticationPrincipal UUID tenantId,
            @PathVariable String userId) {
        return searchService.getUserMemoriesOverview(tenantId, userId);
    }
}
