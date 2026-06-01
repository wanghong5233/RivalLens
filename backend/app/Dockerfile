FROM python:3.11.7-slim

RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    echo "deb http://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list

RUN apt-get update --fix-missing || apt-get update && \
    apt-get install -y --no-install-recommends --fix-missing \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip config set global.index-url "https://mirrors.aliyun.com/pypi/simple/" && \
    pip config set install.trusted-host "mirrors.aliyun.com" && \
    pip install --upgrade pip setuptools wheel

WORKDIR /app

COPY app/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app

RUN sed -i 's/\r$//' /app/start.sh && \
    chmod -R 755 /app && \
    chmod +x /app/start.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/start.sh"]
