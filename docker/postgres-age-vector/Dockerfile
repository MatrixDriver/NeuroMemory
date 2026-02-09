# PostgreSQL 16 with Apache AGE and pgvector
FROM postgres:16

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-server-dev-16 \
    libpq-dev \
    flex \
    bison \
    && rm -rf /var/lib/apt/lists/*

# Install pgvector
RUN cd /tmp && \
    git clone --branch v0.7.0 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make clean && \
    make OPTFLAGS="" && \
    make install && \
    cd / && \
    rm -rf /tmp/pgvector

# Install Apache AGE
RUN cd /tmp && \
    git clone --branch PG16/v1.5.0 https://github.com/apache/age.git && \
    cd age && \
    make PG_CONFIG=/usr/bin/pg_config install && \
    cd / && \
    rm -rf /tmp/age

# Create initialization script
RUN echo "#!/bin/bash" > /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "set -e" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo 'psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL' >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    CREATE EXTENSION IF NOT EXISTS vector;" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    CREATE EXTENSION IF NOT EXISTS age;" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    LOAD 'age';" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    SET search_path = ag_catalog, '\$user', public;" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "    SELECT create_graph('neuromemory_graph');" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    echo "EOSQL" >> /docker-entrypoint-initdb.d/01-init-extensions.sh && \
    chmod +x /docker-entrypoint-initdb.d/01-init-extensions.sh

# Expose PostgreSQL port
EXPOSE 5432

CMD ["postgres"]
