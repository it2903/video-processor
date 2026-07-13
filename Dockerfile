FROM python:3.11-slim-bullseye

RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONPATH="/home/user/app" \
    PYTHONUNBUFFERED=1 \
    MPT_LISTEN_HOST=0.0.0.0 \
    MPT_LISTEN_PORT=8080 \
    MPT_REQUIRE_API_KEY=true

WORKDIR $HOME/app

ARG DOCKER_BUILD_MIRROR=default
ARG PIP_USE_OFFICIAL=1

RUN if [ "$DOCKER_BUILD_MIRROR" = "china" ]; then \
        echo "deb http://mirrors.aliyun.com/debian bullseye main" > /etc/apt/sources.list && \
        echo "deb http://mirrors.aliyun.com/debian-security bullseye-security main" >> /etc/apt/sources.list; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY --chown=user requirements.txt ./

RUN if [ "$PIP_USE_OFFICIAL" = "1" ]; then \
        pip install --no-cache-dir --retries 3 --timeout 60 -r requirements.txt; \
    else \
        pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --retries 3 --timeout 60 -r requirements.txt || \
        pip install --no-cache-dir -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/ --trusted-host mirrors.tuna.tsinghua.edu.cn --retries 3 --timeout 60 -r requirements.txt || \
        pip install --no-cache-dir --retries 3 --timeout 60 -r requirements.txt; \
    fi

COPY --chown=user . .

RUN if [ ! -f config.toml ] && [ -f config.example.toml ]; then \
        cp config.example.toml config.toml; \
    fi && \
    mkdir -p storage logs && \
    if [ -f config.toml ]; then chown user:user config.toml; fi && \
    chown -R user:user storage logs

EXPOSE 8080

USER user

CMD ["python", "main.py"]
