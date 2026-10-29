FROM python:3.13.12-slim
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Universal AI Kit runtime" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="GPL-3.0-only"
WORKDIR /app
COPY apps/runtime/requirements.txt ./
COPY packages/core /opt/uai-core
COPY packages/plugin-sdk /opt/uai-plugin-sdk
COPY plugins/examples/hello /opt/uai-plugin-hello
COPY configs/plugins ./configs/plugins
RUN pip install --no-cache-dir -r requirements.txt /opt/uai-core /opt/uai-plugin-sdk /opt/uai-plugin-hello && useradd --uid 10001 --create-home uai \
    && install -d -o uai -g uai /var/lib/uai/blobs
COPY apps/runtime/uai_runtime ./uai_runtime
USER uai
EXPOSE 8000
CMD ["uvicorn", "uai_runtime.app:from_env", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "32", "--timeout-graceful-shutdown", "130"]

COPY LICENSE /usr/share/licenses/universal-ai-kit/LICENSE
