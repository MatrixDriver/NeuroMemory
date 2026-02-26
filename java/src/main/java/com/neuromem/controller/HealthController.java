package com.neuromem.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

/**
 * Health check endpoints.
 */
@RestController
@RequestMapping
public class HealthController {

    @GetMapping("/")
    public Mono<Map<String, String>> root() {
        return Mono.just(Map.of(
            "service", "neuromem",
            "version", "2.0.0"
        ));
    }

    @GetMapping("/v1/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of(
            "status", "healthy",
            "database", "connected",
            "version", "2.0.0"
        ));
    }
}
