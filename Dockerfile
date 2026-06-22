# NEOS Pi runtime + broker (S0.1). Secrets are INJECTED at runtime (Docker secrets /
# AWS Secrets Manager / env) — NEVER baked in. No .env is copied (see .dockerignore).
FROM python:3.12-slim

WORKDIR /app

# Dependencies first (layer cache). PyYAML + cryptography are import-time;
# anthropic + boto3 are lazy/credential-gated.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code only — no secrets, no fixtures-of-record beyond what runs need.
COPY runtime ./runtime
COPY frontdoor ./frontdoor
COPY acp ./acp
COPY nrt ./nrt
COPY agents ./agents
COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CLASSIFIER_PROVIDER=anthropic

# entrypoint loads injected secrets, runs the credential-gated self-check, then execs CMD.
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

# No long-running transport yet (arrives in S0.3 / nc-channels). Until then the container
# self-checks then idles, ready for `docker exec ... python -m nrt.cli suite agents`.
CMD ["sh", "-c", "echo '[runtime] boot self-check passed; idle — transport arrives in S0.3 (nc-channels). Run: docker exec <ctr> python -m nrt.cli suite agents'; exec tail -f /dev/null"]
