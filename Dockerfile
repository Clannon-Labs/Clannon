FROM python:3.11-slim
WORKDIR /vraksha

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libimage-exiftool-perl \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core/ ./core/
COPY foundation/ ./foundation/
COPY security/ ./security/
COPY get_root.py .
RUN mkdir -p /vraksha/memory /vraksha/workspace /vraksha/rules
COPY main.py .
COPY vraksha.sh . 
COPY models.yaml .

CMD ["python", "main.py"]
