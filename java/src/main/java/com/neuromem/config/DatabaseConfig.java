package com.neuromem.config;

import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;
import org.springframework.r2dbc.connection.init.ConnectionFactoryInitializer;
import org.springframework.r2dbc.connection.init.ResourceDatabasePopulator;

/**
 * Database configuration for R2DBC reactive PostgreSQL connection.
 */
@Configuration
public class DatabaseConfig extends AbstractR2dbcConfiguration {

    /**
     * Initialize database schema on startup.
     * Executes schema.sql if present.
     */
    @Bean
    public ConnectionFactoryInitializer initializer(ConnectionFactory connectionFactory) {
        ConnectionFactoryInitializer initializer = new ConnectionFactoryInitializer();
        initializer.setConnectionFactory(connectionFactory);

        ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
        // Uncomment to run schema.sql on startup
        // populator.addScript(new ClassPathResource("schema.sql"));
        initializer.setDatabasePopulator(populator);

        return initializer;
    }

    @Override
    public ConnectionFactory connectionFactory() {
        // This is handled by Spring Boot auto-configuration
        throw new UnsupportedOperationException("Use Spring Boot auto-configured ConnectionFactory");
    }
}
