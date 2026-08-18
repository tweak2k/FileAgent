FROM python:3.14-slim

WORKDIR /srv

COPY pyproject.toml /srv/pyproject.toml
COPY api /srv/api
COPY ui /srv/ui

RUN pip install --no-cache-dir -e "/srv[ui]"

ENV PYTHONPATH=/srv

EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
