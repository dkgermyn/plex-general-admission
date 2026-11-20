FROM python:3.15.2-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg curl \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
RUN pip install --no-cache-dir .
COPY app ./app
RUN useradd --uid 1000 --create-home app && mkdir -p /app/data /prerolls /trash && chown -R app:app /app /prerolls /trash
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*"]
