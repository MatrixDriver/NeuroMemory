# PostgreSQL 18 with pgvector and pg_search (ParadeDB)
# ParadeDB already includes pgvector and pg_search
FROM paradedb/paradedb:latest

# Create initialization script
RUN echo "#!/bin/bash" > /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "set -e" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo 'psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL' >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    CREATE EXTENSION IF NOT EXISTS vector;" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    CREATE EXTENSION IF NOT EXISTS pg_search;" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "EOSQL" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    chmod +x /docker-entrypoint-initdb.d/01-init-extensions.sh

EXPOSE 5432

CMD ["postgres"]
