package com.neuromem;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;

/**
 * neuromem Server Application
 *
 * Memory-as-a-Service API Server built with Spring Boot WebFlux
 * for high-performance reactive processing.
 */
@SpringBootApplication
@EnableR2dbcRepositories
public class NeuromemApplication {

    public static void main(String[] args) {
        SpringApplication.run(NeuromemApplication.class, args);
    }

}
