FROM python:3.13.12-slim
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Universal AI Kit isolated plugin" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="GPL-3.0-only"
WORKDIR /app
COPY plugins/examples/isolated-http/server.py /app/server.py
COPY configs/plugins/isolated-example.json /app/manifest.json
RUN useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin uai-plugin
USER uai-plugin
EXPOSE 8090
CMD ["python", "-u", "/app/server.py"]

COPY LICENSE /usr/share/licenses/universal-ai-kit/LICENSE
