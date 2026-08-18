FROM python:3.14-slim

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /srv/pyproject.toml
COPY api /srv/api

RUN pip install --no-cache-dir -e "/srv"

WORKDIR /srv/api
COPY api/entrypoint.sh /srv/api/entrypoint.sh
RUN chmod +x /srv/api/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/srv/api/entrypoint.sh"]
