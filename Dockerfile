FROM python:3.12-slim@sha256:d764629ce0ddd8c71fd371e9901efb324a95789d2315a47db7e4d27e78f1b0e9

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Install runtime + optional Anthropic dep so demo_agent.py can use Claude
# if ANTHROPIC_API_KEY is present without a rebuild
RUN pip install --no-cache-dir -e ".[anthropic]"

COPY examples/ examples/

ENV REDIS_HOST=redis
ENV CORTEX_IDENTITY=demo-agent

CMD ["python", "examples/demo_agent.py"]
