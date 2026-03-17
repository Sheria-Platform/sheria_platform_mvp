# Makefile

.PHONY: help install install-dev dev up down deploy test infra \
        lint format type-check pre-commit-install pre-commit-run

help:
	@echo "RAG Platform Commands:"
	@echo "  make install            - Install Python dependencies"
	@echo "  make install-dev        - Install dev tooling (ruff, mypy, pre-commit, etc.)"
	@echo "  make dev                - Run FastAPI server locally"
	@echo "  make up                 - Start local DBs (Docker)"
	@echo "  make down               - Stop local DBs"
	@echo "  make deploy             - Deploy to AWS EKS via Helm"
	@echo "  make infra              - Apply Terraform"
	@echo "  make lint               - Run ruff linter"
	@echo "  make format             - Run ruff formatter + auto-fix"
	@echo "  make type-check         - Run mypy on services/api + libs"
	@echo "  make pre-commit-install - Install git hooks"
	@echo "  make pre-commit-run     - Run all hooks against every file"

install:
	pip install -r services/api/requirements.txt
	pip install -r models/requirements.txt
	pip install -r pipelines/ingestion/requirements.txt # (Hypothetical separate deps)

# Run Local Development Environment
up:
	docker-compose up -d

down:
	docker-compose down

# Run the API locally (Hot Reload)
dev:
	uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env

# Infrastructure
infra:
	cd infra/terraform && terraform init && terraform apply

# Kubernetes Deployment
deploy:
	# Update dependencies
	helm dependency update deploy/helm/api
	# Install/Upgrade
	helm upgrade --install api deploy/helm/api --namespace default
	helm upgrade --install ray-cluster kuberay/ray-cluster -f deploy/ray/ray-cluster.yaml

test:
	pytest tests/

install-dev:
	pip install -r requirements-dev.txt

pre-commit-install:
	pre-commit install
	@echo "Pre-commit hooks installed."

pre-commit-run:
	pre-commit run --all-files

lint:
	ruff check services/ libs/ pipelines/ scripts/ tests/

format:
	ruff format services/ libs/ pipelines/ scripts/ tests/
	ruff check --fix services/ libs/ pipelines/ scripts/ tests/

type-check:
	mypy services/api/ libs/ --config-file pyproject.toml
