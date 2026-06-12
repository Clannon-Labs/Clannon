FROM python:3.12-slim
WORKDIR /vraksha

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libimage-exiftool-perl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# current layout — compose live-mounts the repo over this at runtime,
# the COPYs just make the image self-contained
COPY foundation/ ./foundation/
COPY registry/ ./registry/
COPY core/ ./core/
COPY security/ ./security/
COPY delivery/ ./delivery/
COPY tools/ ./tools/
COPY experts/ ./experts/
COPY prompts/ ./prompts/
COPY main.py models.yaml ./

# run as an unprivileged user: if anything in the pipeline is ever exploited,
# the blast radius is a non-root uid that owns only its own work dirs — not root
RUN mkdir -p /vraksha/workspace /vraksha/rules /vraksha/assets \
    && useradd --create-home --uid 10001 vraksha \
    && chown -R vraksha:vraksha /vraksha
USER vraksha

CMD ["python", "main.py"]
