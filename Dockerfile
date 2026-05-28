FROM python:3.14.5-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN pip install poetry && poetry lock && poetry install --no-root --only=main

COPY nukiblinker ./nukiblinker

EXPOSE 8080

ENTRYPOINT [ "poetry", "run", "python", "-m", "nukiblinker", "--config", "/app/config.yaml" ]
