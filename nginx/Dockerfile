# syntax=docker/dockerfile:1.7
FROM nginx:1.27-alpine

RUN --mount=type=cache,target=/var/cache/apk \
    sed -i 's|dl-cdn.alpinelinux.org|mirror.arvancloud.ir/alpine|g' /etc/apk/repositories \
    && apk add --no-cache curl

COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80
