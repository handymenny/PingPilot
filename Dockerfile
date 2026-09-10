FROM python:3.14-alpine

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN apk add --no-cache \
        ca-certificates \
        curl \
        fping \
        knot-utils \
        mtr \
        traceroute \
    && curl -fsSL https://raw.githubusercontent.com/deajan/tcpping/master/tcpping -o /usr/local/bin/tcpping \
    && chmod 755 /usr/local/bin/tcpping \
    && pip install --no-cache-dir -r requirements.txt

COPY monitor.py ./
COPY monitoring ./monitoring

ENTRYPOINT ["python", "monitor.py", "--config", "/app/config.yaml"]
