# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS build

ARG NPM_REGISTRY=https://package-mirror.liara.ir/repository/npm/
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY}

WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/sources.list.d/* \
    && printf 'deb http://mirror.arvancloud.ir/debian bookworm main\ndeb http://mirror.arvancloud.ir/debian-security bookworm-security main\n' > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --registry ${NPM_REGISTRY}

COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
