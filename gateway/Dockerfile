FROM python:3.12-slim

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY gateway/ gateway/

# Data directory for state persistence
RUN useradd -r -s /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

ENV PG_MCP_STATE_FILE=/data/db_state.json
ENV PG_MCP_PORT=8090
ENV PYTHONUNBUFFERED=1

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.environ.get('PG_MCP_PORT','8090')+'/health')" || exit 1

USER appuser

CMD ["python", "-m", "gateway"]
