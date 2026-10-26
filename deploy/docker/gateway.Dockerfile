FROM golang:1.27.1-alpine AS build
WORKDIR /src
COPY apps/gateway/go.mod apps/gateway/go.sum ./
RUN go mod download
COPY apps/gateway/ .
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /gateway .
FROM alpine:3.23.3
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Universal AI Kit gateway" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="Proprietary"
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 uai
COPY --from=build /gateway /usr/local/bin/gateway
USER uai
EXPOSE 8080
ENTRYPOINT ["gateway"]
