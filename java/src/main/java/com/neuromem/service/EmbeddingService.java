package com.neuromem.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

/**
 * Service for generating embeddings using external API (SiliconFlow).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EmbeddingService {

    private final WebClient.Builder webClientBuilder;

    @Value("${neuromem.embedding.api-url}")
    private String apiUrl;

    @Value("${neuromem.embedding.api-key}")
    private String apiKey;

    @Value("${neuromem.embedding.model}")
    private String model;

    /**
     * Generate embedding vector for text content.
     *
     * @param text Input text
     * @return Embedding vector as float array
     */
    public Mono<float[]> generateEmbedding(String text) {
        WebClient webClient = webClientBuilder.baseUrl(apiUrl).build();

        Map<String, Object> requestBody = Map.of(
                "model", model,
                "input", text,
                "encoding_format", "float"
        );

        return webClient.post()
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(Map.class)
                .map(response -> {
                    // Parse response to extract embedding
                    @SuppressWarnings("unchecked")
                    List<Map<String, Object>> data = (List<Map<String, Object>>) response.get("data");
                    if (data != null && !data.isEmpty()) {
                        @SuppressWarnings("unchecked")
                        List<Double> embedding = (List<Double>) data.get(0).get("embedding");
                        return embedding.stream()
                                .map(Double::floatValue)
                                .toArray(i -> new float[i]);
                    }
                    throw new RuntimeException("Invalid embedding response");
                })
                .doOnError(error -> log.error("Failed to generate embedding", error));
    }
}
