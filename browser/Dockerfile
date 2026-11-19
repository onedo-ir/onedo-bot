# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ARG PIP_INDEX_URL=https://package-mirror.liara.ir/repository/pypi/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Keep apt .debs so BuildKit cache mounts actually speed up rebuilds
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/sources.list.d/* \
    && printf 'deb http://mirror.arvancloud.ir/debian bookworm main\ndeb http://mirror.arvancloud.ir/debian-security bookworm-security main\n' > /etc/apt/sources.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-color-emoji \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        xdg-utils

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Chromium is large; reuse BuildKit cache across rebuilds, then copy into the image layer
RUN --mount=type=cache,id=onedo-playwright-chromium,target=/cache/pw,sharing=locked \
    mkdir -p /ms-playwright \
    && if [ -n "$(ls -A /cache/pw 2>/dev/null)" ]; then cp -a /cache/pw/. /ms-playwright/; fi \
    && playwright install chromium \
    && find /cache/pw -mindepth 1 -delete \
    && cp -a /ms-playwright/. /cache/pw/

COPY app ./app

EXPOSE 3000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
