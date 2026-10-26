FROM python:3.13.12-slim
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Universal AI Kit worker" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="Proprietary"
WORKDIR /app
COPY apps/runtime/requirements.txt ./
COPY apps/worker/requirements.txt ./worker-requirements.txt
COPY packages/core /opt/uai-core
RUN pip install --no-cache-dir -r requirements.txt -r worker-requirements.txt /opt/uai-core && useradd --uid 10001 --create-home uai \
    && install -d -o uai -g uai /var/lib/uai/blobs
COPY apps/runtime/uai_runtime ./uai_runtime
COPY apps/worker/uai_worker ./uai_worker
USER uai
CMD ["python", "-m", "uai_worker.main"]
