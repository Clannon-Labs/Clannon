# Backend image — Railway builds this (root directory = backend/).
# Runs the FastAPI API by default; the same image also carries the CLI (main.py).
FROM python:3.12-slim
WORKDIR /app

# system deps: ffmpeg + exiftool for the media sanitizers, libmagic for MIME sniff
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libimage-exiftool-perl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# deps first for layer caching. requirements.txt pins spaCy en_core_web_lg as a
# wheel URL, so the PII sanitizer's model is baked here (never downloaded mid-run).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# warm the memory embedder into a baked cache so the ~4-min download never happens
# at request time (the cache dir is ephemeral on containers unless baked here).
ENV VRAKSHA_EMBED_CACHE=/app/assets/fastembed_cache
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5', cache_dir='/app/assets/fastembed_cache')"

# the app (see .dockerignore — secrets, the prompts.secure overlay, tests, and
# local caches are NOT baked in; prompts.secure is provided at deploy time)
COPY . .

# fail closed in prod if a locked prompt (verifier/filter) is still on its baseline
ENV VRAKSHA_REQUIRE_PROD_PROMPTS=1

# run as an unprivileged user: if the pipeline is ever exploited, the blast radius
# is a non-root uid that owns only its own work dirs, not root
RUN mkdir -p /app/workspace /app/rules /app/api/data \
    && useradd --create-home --uid 10001 vraksha \
    && chown -R vraksha:vraksha /app
USER vraksha

# Railway provides $PORT; default to 8000 for local `docker run`
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
