# syntax=docker/dockerfile:1.7
FROM nginx:1.27-alpine

RUN --mount=type=cache,target=/var/cache/apk,sharing=locked \
    apk add --no-cache curl

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
