# neuromem Java Server

High-performance Memory-as-a-Service API server built with Spring Boot WebFlux.

## Tech Stack

- **Spring Boot 3.2.2** - Framework
- **Spring WebFlux** - Reactive web framework for high concurrency
- **Spring Data R2DBC** - Reactive database access
- **PostgreSQL 16** - Database with pgvector extension
- **Lombok** - Reduce boilerplate code
- **Maven** - Build tool

## Performance Target

- **> 10,000 QPS** - Designed for high throughput
- **Reactive** - Non-blocking I/O for efficient resource usage
- **Connection Pooling** - Optimized database connections

## Project Structure

```
src/main/java/com/neuromem/
├── neuromemApplication.java    # Main application entry point
├── config/                         # Configuration classes
│   ├── DatabaseConfig.java
│   └── SecurityConfig.java
├── controller/                     # REST API controllers
│   ├── HealthController.java
│   ├── TenantController.java
│   ├── PreferenceController.java
│   ├── SearchController.java
│   └── GraphController.java
├── service/                        # Business logic
├── repository/                     # Data access layer
├── model/
│   ├── entity/                     # Database entities
│   └── dto/                        # Data transfer objects
└── security/                       # Authentication & authorization
```

## Quick Start

### Prerequisites

- Java 17 or higher
- Maven 3.8+
- PostgreSQL 16 with pgvector extension

### Build

```bash
cd java
mvn clean install
```

### Run

```bash
mvn spring-boot:run
```

Or run the JAR:

```bash
java -jar target/neuromem-server-2.0.0.jar
```

### Configuration

Set environment variables or edit `src/main/resources/application.yml`:

```bash
export DATABASE_HOST=localhost
export DATABASE_PORT=5432
export DATABASE_NAME=neuromem
export DATABASE_USER=neuromem
export DATABASE_PASSWORD=neuromem
export SILICONFLOW_API_KEY=your-api-key
export SERVER_PORT=8765
```

## API Endpoints

- `GET /` - Service info
- `GET /v1/health` - Health check
- `POST /v1/tenants/register` - Register tenant
- `POST /v1/preferences` - Set preference
- `GET /v1/preferences` - List preferences
- `POST /v1/search` - Semantic search
- `POST /v1/graph/nodes` - Create graph node
- `POST /v1/graph/edges` - Create graph edge

## Testing

```bash
mvn test
```

## Development

The project uses Spring Boot DevTools for hot reload during development.

## Compatibility

The Java server is fully compatible with the existing Python SDK (`sdk/neuromem/`). No changes needed on the client side.
