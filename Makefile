install:
	poetry install
	poetry lock

test:
	poetry run pytest -rP

coverage:
	poetry run pytest --cov=nukiblinker --cov-report=term-missing --cov-report=xml:coverage.xml

lint:
	poetry run flake8 --show-source

format:
	poetry run black --diff .

clean:
	find . -type d -name '__pycache__' -exec rm -rf {} +

build:
	docker build --tag nukiblinker .

run:
	docker run --network host -v $(PWD)/config.yaml:/app/config.yaml:ro nukiblinker

runLocal:
	poetry run python -m nukiblinker --config config.yaml

cleanup-branches:
	powershell -ExecutionPolicy Bypass -File script/cleanup-branches.ps1
