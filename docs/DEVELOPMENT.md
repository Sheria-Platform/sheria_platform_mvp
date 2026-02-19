# Development Guide — Sheria Platform

This guide covers everything needed to develop and extend the Sheria Platform: local setup without Docker, code style conventions, adding LangGraph nodes, adding API routes, running tests, and the PR process.

---

## Table of Contents

1. [Local Setup](#1-local-setup)
2. [Running Without Docker](#2-running-without-docker)
3. [Code Style](#3-code-style)
4. [Adding a New LangGraph Node](#4-adding-a-new-langgraph-node)
5. [Adding a New API Route](#5-adding-a-new-api-route)
6. [Running Tests](#6-running-tests)
7. [Pull Request Process](#7-pull-request-process)
8. [Architecture Decisions](#8-architecture-decisions)

---

## 1. Local Setup

### Clone and create a virtual environment

```bash
git clone https://github.com/sheria-platform/judicial-mvp.git
cd sheria_platform_mvp

python3.11 -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows PowerShell
```

### Install dependencies

```bash
# API service
pip install -r services/api/requirements.txt

# Ingestion pipeline
pip install -r pipelines/ingestion/requirements.txt

# Development tools (linters, formatters, testing)
pip install black ruff pytest pytest-asyncio httpx pytest-cov
```

### Configure pre-commit hooks

Pre-commit hooks run `ruff` and `black` automatically on every commit, preventing style violations from entering the repository.

```bash
pip install pre-commit
pre-commit install
```

To run all hooks manually against all files:

```bash
pre-commit run --all-files
```

### Configure the environment file

```bash
cp .env.example .env
# Edit .env with your local credentials
```

---

## 2. Running Without Docker

You can run each service independently on the host when you want faster iteration or when debugging a specific component. You still need the data stores (Postgres, Redis, Qdrant, Neo4j, MinIO, Ollama) running — the easiest way is to start only the infrastructure containers and run the Python processes outside Docker.

### Start only infrastructure services

```bash
docker compose up -d postgres redis qdrant neo4j minio ollama
```

### Set environment variables

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/sheria_judicial_db"
export REDIS_URL="redis://localhost:6379/0"
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="sheriapassword"
export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_LLM_MODEL="llama3.3"
export OLLAMA_EMBED_MODEL="nomic-embed-text"
export JWT_SECRET_KEY="$(openssl rand -base64 64)"
export LOG_LEVEL="DEBUG"
export RELOAD="true"
```

### Run the FastAPI server

```bash
uvicorn services.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  --log-level debug
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### Run the ingestion pipeline

```bash
# Ingest from a specific MinIO bucket and prefix
python pipelines/ingestion/main.py kenya-law-reports supreme-court/

# Ingest test data
python testExample/minio_ingestion.py
```

### Test the Ollama connection

```bash
curl http://localhost:11434/api/tags
```

---

## 3. Code Style

### Standards

- **Style guide**: PEP 8 with a maximum line length of **88 characters** (Black default).
- **Formatter**: [Black](https://black.readthedocs.io/) — no configuration needed; run it and commit.
- **Linter**: [Ruff](https://docs.astral.sh/ruff/) — covers flake8, isort, pyupgrade, and more in one tool.
- **Docstrings**: [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
- **Type hints**: Required on all public functions and class methods.

### Running the formatters

```bash
# Format all Python files
black .

# Check formatting without modifying files
black --check .

# Lint and auto-fix where possible
ruff check . --fix

# Lint without fixing (for CI)
ruff check .
```

### Docstring example

```python
def search_case_law(
    query: str,
    top_k: int = 5,
    jurisdiction: list[str] | None = None,
) -> list[CaseLawResult]:
    # Search Kenya Law Reports for cases relevant to the query.
    #
    # Performs a cosine similarity search against the Qdrant collection
    # and reranks results by court hierarchy (Supreme Court > Court of
    # Appeal > High Court).
    #
    # Args:
    #     query: Plain-English legal research question.
    #     top_k: Maximum number of results to return.
    #     jurisdiction: Optional list of courts to restrict the search.
    #         Accepted values: "Supreme Court", "Court of Appeal",
    #         "High Court". If None, all courts are searched.
    #
    # Returns:
    #     A list of CaseLawResult objects ordered by relevance score
    #     descending.
    #
    # Raises:
    #     QdrantConnectionError: If the Qdrant service is unreachable.
    #     EmbeddingError: If the Ollama embedding service fails.
    ...
```

> Note: In actual code, use triple-quote docstrings following the Google style. The `#` comment style above is used only to avoid formatting conflicts in this Markdown file.

### Import ordering

Ruff enforces isort-compatible import ordering. The expected order is:

1. Standard library imports
2. Third-party imports
3. Local application imports

```python
# Correct
import json
import logging
from typing import Any

import httpx
from fastapi import HTTPException
from qdrant_client import QdrantClient

from libs.schemas.legal_research import CaseLawResult
from services.api.app.clients.qdrant import get_qdrant_client
```

---

## 4. Adding a New LangGraph Node

The LangGraph pipeline is defined in `services/api/app/agents/`. Each agent is a compiled `StateGraph` where nodes are async functions that receive and return the agent state.

### Step 1: Define the state extension (if needed)

If your node requires new state fields, add them to the shared state dataclass in `services/api/app/agents/state.py`:

```python
# services/api/app/agents/state.py
from dataclasses import dataclass, field

@dataclass
class AgentState:
    query: str = ""
    refined_query: str = ""
    retrieved_chunks: list[dict] = field(default_factory=list)
    citation_graph: list[dict] = field(default_factory=list)
    # Add your new field here:
    statutory_references: list[str] = field(default_factory=list)
    answer_tokens: list[str] = field(default_factory=list)
    error: str | None = None
```

### Step 2: Create the node function

Create a new file in `services/api/app/agents/nodes/`:

```python
# services/api/app/agents/nodes/statutory_search_node.py
import logging
from services.api.app.agents.state import AgentState
from services.api.app.tools.statutory_search import search_statutes

logger = logging.getLogger(__name__)


async def statutory_search_node(state: AgentState) -> AgentState:
    # Query Kenya Law statutes database for relevant legislation.
    #
    # Args:
    #     state: Current pipeline agent state containing the refined query.
    #
    # Returns:
    #     Updated state with statutory_references populated.
    logger.info("Statutory search node: querying '%s'", state.refined_query)

    try:
        statutes = await search_statutes(
            query=state.refined_query,
            top_k=3,
        )
        return AgentState(
            **{**state.__dict__, "statutory_references": statutes}
        )
    except Exception as exc:
        logger.error("Statutory search failed: %s", exc, exc_info=True)
        # Return state unmodified so the pipeline continues
        return state
```

### Step 3: Register the node in the graph

Open the agent graph file (`services/api/app/agents/legal_research.py`) and add the node:

```python
from services.api.app.agents.nodes.statutory_search_node import statutory_search_node

# Inside the graph builder function:
graph_builder.add_node("statutory_search", statutory_search_node)

# Add an edge from the retriever to your new node
graph_builder.add_edge("retriever", "statutory_search")

# Connect your node to the next stage
graph_builder.add_edge("statutory_search", "analyzer")
```

### Step 4: Write a unit test

```python
# tests/agents/test_statutory_search_node.py
import pytest
from unittest.mock import AsyncMock, patch
from services.api.app.agents.nodes.statutory_search_node import statutory_search_node
from services.api.app.agents.state import AgentState


@pytest.mark.asyncio
async def test_statutory_search_node_success():
    initial_state = AgentState(
        query="adverse possession test Kenya",
        refined_query="adverse possession continuous possession Kenya",
    )
    mock_statutes = ["Land Registration Act, Cap 300, s. 28"]

    with patch(
        "services.api.app.agents.nodes.statutory_search_node.search_statutes",
        new_callable=AsyncMock,
        return_value=mock_statutes,
    ):
        result = await statutory_search_node(initial_state)

    assert result.statutory_references == mock_statutes


@pytest.mark.asyncio
async def test_statutory_search_node_handles_tool_error():
    initial_state = AgentState(refined_query="adverse possession")

    with patch(
        "services.api.app.agents.nodes.statutory_search_node.search_statutes",
        new_callable=AsyncMock,
        side_effect=ConnectionError("Statutes DB unreachable"),
    ):
        result = await statutory_search_node(initial_state)

    # Node must return unmodified state on error, not propagate the exception
    assert result.statutory_references == []
```

---

## 5. Adding a New API Route

### Step 1: Create the route file

```python
# services/api/app/routes/predict.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from services.api.app.auth.dependencies import require_role
from services.api.app.models.predict import CasePredictionRequest, CasePredictionResponse
from services.api.app.tools.predict_case_duration import predict_duration

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/predict", tags=["Prediction"])


@router.post(
    "/case-duration",
    response_model=CasePredictionResponse,
    summary="Predict case duration",
)
async def predict_case_duration(
    request: CasePredictionRequest,
    current_user=Depends(require_role(["judge", "magistrate"])),
) -> CasePredictionResponse:
    logger.info(
        "Duration prediction by user=%s case_type=%s",
        current_user.id,
        request.case_type,
    )
    try:
        return await predict_duration(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Prediction failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prediction service temporarily unavailable.",
        ) from exc
```

### Step 2: Create the Pydantic request/response models

```python
# services/api/app/models/predict.py
from pydantic import BaseModel, Field


class CasePredictionRequest(BaseModel):
    case_type: str = Field(..., examples=["land_dispute", "criminal", "family"])
    parties_count: int = Field(..., ge=2, le=50)
    complexity: str = Field(..., pattern="^(low|medium|high)$")
    court: str = Field(..., examples=["High Court Nairobi"])


class CasePredictionResponse(BaseModel):
    estimated_months_min: int
    estimated_months_max: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    similar_cases_analyzed: int
    contributing_factors: list[str]
```

### Step 3: Register the router in main.py

```python
# services/api/main.py
from services.api.app.routes.predict import router as predict_router

app.include_router(predict_router, prefix="/api/v1")
```

### Step 4: Write an integration test

```python
# tests/routes/test_predict.py
import pytest
from httpx import AsyncClient
from services.api.main import app


@pytest.mark.asyncio
async def test_predict_case_duration_returns_200(test_client: AsyncClient):
    response = await test_client.post(
        "/api/v1/predict/case-duration",
        json={
            "case_type": "land_dispute",
            "parties_count": 4,
            "complexity": "high",
            "court": "High Court Nairobi",
        },
        headers={"Authorization": "Bearer <test-token>"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "estimated_months_min" in data
    assert 0.0 <= data["confidence"] <= 1.0
```

---

## 6. Running Tests

Tests live in the `tests/` directory, mirroring the source tree structure.

```
tests/
├── agents/
│   ├── test_planner_node.py
│   ├── test_retriever_node.py
│   └── test_statutory_search_node.py
├── routes/
│   ├── test_chat.py
│   ├── test_feedback.py
│   └── test_predict.py
├── tools/
│   ├── test_vector_search.py
│   └── test_graph_search.py
├── ingestion/
│   ├── test_pdf_loader.py
│   └── test_chunking.py
└── conftest.py
```

### Run all tests

```bash
pytest tests/ -v
```

### Run a specific test file

```bash
pytest tests/agents/test_statutory_search_node.py -v
```

### Run tests with a coverage report

```bash
pytest tests/ \
  --cov=services \
  --cov=pipelines \
  --cov-report=term-missing \
  --cov-report=html

# Open htmlcov/index.html to browse coverage by file
```

### Run only unit tests (skip slow integration tests)

```bash
pytest tests/ -v -m "not integration"
```

Mark slow tests:

```python
@pytest.mark.integration
async def test_end_to_end_legal_research():
    ...
```

### Shared fixtures (conftest.py)

```python
# tests/conftest.py
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock
from services.api.main import app


@pytest.fixture
def mock_qdrant_client():
    client = AsyncMock()
    client.search.return_value = []
    return client


@pytest.fixture
async def test_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
```

---

## 7. Pull Request Process

### Branch naming convention

```
feat/<short-description>        # New feature
fix/<short-description>         # Bug fix
refactor/<short-description>    # Refactoring without behavior change
docs/<short-description>        # Documentation only
test/<short-description>        # Tests only
chore/<short-description>       # Build system, dependencies, CI changes
```

Examples:

```
feat/add-statutory-search-node
fix/qdrant-connection-timeout
docs/update-api-reference
```

### Commit message format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>

<body - explain WHY, not WHAT>

<footer - breaking changes, issue references>
```

Examples:

```
feat(agents): add statutory search node to LangGraph pipeline

Kenya Law statutes were not being referenced in legal research responses.
This node queries a statutes index in Qdrant and appends relevant legislation
to the agent state before the Responder node runs.

Closes #42
```

```
fix(ingestion): handle PDF files with no extractable text

Some scanned PDFs returned empty strings from pdfminer. Added a fallback
to log a warning and skip the document rather than crashing the pipeline.
```

### PR checklist

Before opening a Pull Request, verify:

- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New functionality has corresponding unit and/or integration tests
- [ ] Code is formatted: `black --check .`
- [ ] No lint errors: `ruff check .`
- [ ] Google-style docstrings on all new public functions and classes
- [ ] Type hints on all new function signatures
- [ ] `.env.example` updated if new environment variables were added
- [ ] `docs/CONFIGURATION.md` updated if configuration changed
- [ ] `docs/API.md` updated if endpoint request/response schemas changed
- [ ] No hardcoded credentials, API keys, or IP addresses
- [ ] No `print()` statements in production code (use `logging` module)

### Review and merge process

1. Open a PR against `main` with a clear title and description explaining the motivation.
2. At least one team member must review and approve before merging.
3. All CI checks (lint, test, Docker build) must pass.
4. Squash-merge into `main` to maintain a clean, linear commit history.

---

## 8. Architecture Decisions

### Why Ollama instead of Ray Serve for LLM inference?

**Decision**: Ollama is used for both LLM inference and embeddings in the current MVP.

**Rationale**: Ray Serve with vLLM is the production target (defined in `models/` and `deploy/ray/`), but requires NVIDIA GPU infrastructure that is not universally available during development. Ollama provides a simple, Docker-friendly alternative that runs on CPU (including Apple Silicon) with zero infrastructure overhead. The client interface is fully abstracted in `services/api/app/clients/`, making it straightforward to swap Ollama for a Ray Serve endpoint by changing a single environment variable — from `OLLAMA_BASE_URL` to `RAY_LLM_ENDPOINT` — without modifying any agent or tool code.

### Why LangGraph instead of a simple chain?

**Decision**: LangGraph is used for the judicial RAG pipeline rather than a linear LangChain LCEL chain or custom async orchestration.

**Rationale**: Legal research is not a single-step process. It requires multiple retrieval strategies (vector search, graph traversal, statutory lookup), conditional branching (if vector search returns low-confidence results, broaden the search parameters), and potentially multiple passes through the analyzer node when additional context is needed. LangGraph's directed graph model makes control flow explicit, debuggable at the node level, and independently testable per node. The streaming SSE output also maps naturally to LangGraph's node-by-node execution model, enabling the API to emit `status` events as each stage begins.

### Why both Qdrant and Neo4j?

**Decision**: The retrieval layer uses Qdrant for dense vector search and Neo4j for citation graph traversal — a hybrid approach.

**Rationale**: Dense vector search (Qdrant) excels at semantic similarity: finding cases that discuss the same legal concept even when the wording differs. However, it cannot answer structural queries such as "Which Supreme Court cases directly overruled this judgment?" or "Trace the evolution of adverse possession doctrine through the citation chain." Neo4j's property graph model answers these queries natively and efficiently with Cypher. The two databases are complementary: vector search surfaces semantically relevant cases, and graph traversal confirms binding precedent status. Combining them produces substantially higher recall and precision than either alone for judicial research tasks.

### Why FastAPI over Django REST Framework?

**Decision**: FastAPI is the API framework.

**Rationale**: The streaming SSE endpoint (`/api/v1/chat/stream`) is a core, differentiating feature. FastAPI's first-class `StreamingResponse` and native `async/await` support make long-lived streaming connections straightforward to implement and reason about. FastAPI also generates OpenAPI documentation automatically from type annotations and validates request/response bodies via Pydantic — schemas that are already shared between the API layer and the ingestion pipeline through `libs/schemas/`. Django REST Framework would require additional packages to support async streaming and does not integrate as naturally with the Pydantic-centric codebase.
