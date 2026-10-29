FROM node:24-alpine AS build
WORKDIR /src
COPY packages/sdk-typescript packages/sdk-typescript
COPY apps/console apps/console
RUN npm ci --prefix packages/sdk-typescript
RUN npm ci --prefix apps/console
RUN npm --prefix apps/console run build

FROM node:24-alpine
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="Universal AI Kit console" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.licenses="GPL-3.0-only"
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=build /src/apps/console/build ./build
COPY --from=build /src/apps/console/package.json ./package.json
EXPOSE 3000
USER node
CMD ["node", "build"]

COPY LICENSE /usr/share/licenses/universal-ai-kit/LICENSE
