package com.neuromem.controller;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;
import com.neuromem.security.ApiKeyAuthenticationFilter;

/**
 * Integration tests for HealthController.
 */
@WebFluxTest(controllers = HealthController.class)
@Import({HealthController.class})
class HealthControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private ApiKeyAuthenticationFilter apiKeyAuthenticationFilter;

    @Test
    void root_ReturnsServiceInfo() {
        webTestClient.get()
                .uri("/")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.service").isEqualTo("neuromem")
                .jsonPath("$.version").isEqualTo("2.0.0");
    }

    @Test
    void health_ReturnsHealthStatus() {
        webTestClient.get()
                .uri("/v1/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("healthy")
                .jsonPath("$.version").isEqualTo("2.0.0");
    }
}
