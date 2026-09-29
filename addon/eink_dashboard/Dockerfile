FROM ghcr.io/home-assistant/base:3.24-2026.08.0
RUN apk add --no-cache \
        python3 \
        py3-pip \
        git \
        jpeg-dev \
        zlib-dev \
        gcc \
        musl-dev \
        python3-dev \
        linux-headers \
        font-dejavu \
        tzdata

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt \
    && git clone --depth 1 https://github.com/waveshare/e-Paper /tmp/e-Paper \
    && cp -r /tmp/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd /app/waveshare_epd \
    && rm -rf /tmp/e-Paper
COPY app/ /app/
CMD ["with-contenv", "python3", "/app/main.py"]
