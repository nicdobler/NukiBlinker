FROM python:3.14.5-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only=main

COPY nukiblinker ./nukiblinker

EXPOSE 8080

ENTRYPOINT [ "poetry", "run", "python", "-m", "nukiblinker", "--config", "/app/config.yaml" ]
