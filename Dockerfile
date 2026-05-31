FROM python:3.14.5-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only=main

COPY nukiblinker ./nukiblinker
COPY script/generate_chime.py ./script/generate_chime.py

# Generate default doorbell chime (pure Python, no external deps)
RUN python script/generate_chime.py

EXPOSE 8080

ENTRYPOINT [ "poetry", "run", "python", "-m", "nukiblinker", "--config", "/app/config.yaml" ]
