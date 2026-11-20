# syntax=docker/dockerfile:1.7
FROM node:20-bookworm-slim AS build

ARG NPM_REGISTRY=https://registry.npmjs.org/
ENV NPM_CONFIG_REGISTRY=${NPM_REGISTRY} \
    NPM_CONFIG_FETCH_RETRIES=5 \
    NPM_CONFIG_PREFER_OFFLINE=true

WORKDIR /app

# Keep apt .debs so BuildKit cache mounts actually speed up rebuilds
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates

COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --registry ${NPM_REGISTRY} --prefer-offline

COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
