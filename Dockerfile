FROM python:3.11-slim
WORKDIR /vraksha

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libimage-exiftool-perl \
    clamav \
    clamav-daemon \
    && rm -rf /var/lib/apt/lists/*

# --- SECURITY DEPS (added by security layer setup) ---
RUN mkdir -p /vraksha/security/vendors/pdfid \
    && curl -fsSL https://raw.githubusercontent.com/DidierStevens/DidierStevensSuite/master/pdfid.py \
        -o /vraksha/security/vendors/pdfid/pdfid.py \
    && curl -fsSL https://raw.githubusercontent.com/DidierStevens/DidierStevensSuite/master/pdf-parser.py \
        -o /vraksha/security/vendors/pdfid/pdf-parser.py

RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY get_root.py .
RUN mkdir -p /vraksha/memory /vraksha/workspace
COPY main.py .
COPY vraksha.sh . 
COPY models.yaml .

CMD ["python", "main.py"]
