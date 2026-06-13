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

# --- Mac branch workflow ---------------------------------------------------
# run-tests : lint + tests on the CURRENT branch
# validate  : fetch + pick a branch (menu or arg) + checkout + run-tests
# cleanup   : return to main, pull, and prune merged local branches
run-tests: lint test

validate:
	bash scripts/validate.sh

cleanup:
	git checkout main
	git pull --ff-only
	bash script/cleanup-branches.sh

build:
	docker build --tag nukiblinker .

run:
	docker run --network host -v $(PWD)/config.yaml:/app/config.yaml:ro nukiblinker

runLocal:
	poetry run python -m nukiblinker --config config.yaml

report:
	bash script/test-and-report.sh

cleanup-branches:
	powershell -ExecutionPolicy Bypass -File script/cleanup-branches.ps1

.PHONY: install test coverage lint format clean run-tests validate cleanup build run runLocal report cleanup-branches
