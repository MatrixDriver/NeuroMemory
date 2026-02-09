FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY server/pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy application code
COPY server/ ./server/

EXPOSE 8765

CMD ["uvicorn", "server.app.main:app", "--host", "0.0.0.0", "--port", "8765"]
