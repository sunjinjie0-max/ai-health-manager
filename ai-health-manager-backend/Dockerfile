ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG INSTALL_ML_DEPS=false

WORKDIR /app

RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list.d/debian.sources; \
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list.d/debian.sources; \
    fi \
    && if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.tuna.tsinghua.edu.cn/debian|g' /etc/apt/sources.list; \
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl zlib1g-dev tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt /app/

RUN pip install --no-cache-dir --upgrade pip -i ${PIP_INDEX_URL} --timeout 120 --retries 5 \
    && pip install --no-cache-dir -r /app/requirements.txt -i ${PIP_INDEX_URL} --timeout 120 --retries 5

RUN if [ "${INSTALL_ML_DEPS}" = "true" ]; then \
        pip install --no-cache-dir torch --index-url ${TORCH_INDEX_URL} --timeout 120 --retries 5 \
        && pip install --no-cache-dir -r /app/requirements-ml.txt -i ${PIP_INDEX_URL} --timeout 120 --retries 5; \
    else \
        echo "Skipping optional ML dependencies. Set INSTALL_ML_DEPS=true to enable BGE-M3."; \
    fi

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
