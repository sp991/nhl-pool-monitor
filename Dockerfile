FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATA_DIR=/data CONFIG_PATH=/config/pools.yaml TZ=America/Toronto

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY app ./app
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

VOLUME ["/data", "/config"]
EXPOSE 8501

# Default: collector. The dashboard service overrides the command.
CMD ["python", "-m", "app.collector"]
