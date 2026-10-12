FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 \
    DOCLING_ARTIFACTS_PATH=/models HF_HUB_DISABLE_TELEMETRY=1 \
    XDG_CACHE_HOME=/tmp/cache HF_HOME=/tmp/huggingface TORCH_HOME=/tmp/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 libgl1 tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/document_parser/requirements.txt /app/requirements.txt
# CPU wheels avoid downloading a CUDA runtime for this independent CPU service.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchvision==0.23.0 \
    && pip install --no-cache-dir -r /app/requirements.txt
COPY services/__init__.py /app/services/__init__.py
COPY services/document_parser /app/services/document_parser
# Build-time model fetch has no access to a user's contract. Runtime is offline.
RUN python -m services.document_parser.prefetch \
    && useradd --uid 10001 --create-home parser \
    && chmod -R a+rX /models
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PARSER_DOCUMENT_TIMEOUT_SECONDS=18 PARSER_HARD_TIMEOUT_SECONDS=20
USER 10001
EXPOSE 8090
CMD ["uvicorn", "services.document_parser.app:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "1", "--no-access-log"]
