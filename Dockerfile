FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    PORT=8080 \
    MAINTENANCE_DATA_PATH=/tmp/maintenance.json

WORKDIR /app
COPY src ./src
COPY data ./data

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
CMD ["python", "-m", "src.http_server"]
