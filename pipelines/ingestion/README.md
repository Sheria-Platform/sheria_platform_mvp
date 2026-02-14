# Data Ingestion Pipeline

## Overview

The Sheria Platform ingestion pipeline transforms raw legal documents (court judgments, case law, statutes) into structured, searchable knowledge. It converts unstructured text into:

1. **Vector embeddings** for semantic search (stored in Qdrant)
2. **Knowledge graphs** for relationship mapping (stored in Neo4j)

The pipeline uses **remote Ollama servers** for embeddings and LLM inference, with Ray Data for distributed document processing.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
nano .env  # Update with your values

# 2. Test connectivity
python test_connection.py

# 3. Run ingestion
python main.py <bucket_name> <prefix>
```

## Architecture

Based on the [Scalable Production-Grade Agentic RAG Pipeline](https://freedium-mirror.cfd/building-a-scalable-production-grade-agentic-rag-pipeline-1168dcd36260), our architecture follows this flow:

```
┌─────────────────────────────────────────────────────────┐
│  1. Document Loading (S3/MinIO)                         │
│     ├── PDF (Court Judgments)                           │
│     ├── DOCX (Pleadings, Briefs)                        │
│     └── HTML (Kenya Law Reports)                        │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  2. Parsing & Text Extraction                           │
│     ├── PDF: unstructured library                       │
│     ├── DOCX: python-docx                               │
│     └── HTML: BeautifulSoup                             │
└──────────────────┬──────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────┐
│  3. Chunking (512 tokens, 50 overlap)                   │
│     - Preserves legal context                           │
│     - Maintains case citations                          │
│     - Keeps legal principles intact                     │
└──────────────────┬──────────────────────────────────────┘
                   │
          ┌────────┴────────┐
          │                 │
          ▼                 ▼
┌──────────────────┐  ┌────────────────────┐
│  4A. Embedding   │  │  4B. Graph         │
│      Generation  │  │      Extraction    │
│                  │  │                    │
│  Ollama API      │  │  Ollama LLM API    │
│  nomic-embed-text│  │  llama3            │
│                  │  │                    │
│  → Vector (768d) │  │  → Entities/Edges  │
└────────┬─────────┘  └─────────┬──────────┘
         │                      │
         ▼                      ▼
┌──────────────────┐  ┌────────────────────┐
│  5A. Qdrant      │  │  5B. Neo4j         │
│      Indexing    │  │      Indexing      │
│                  │  │                    │
│  Collection:     │  │  Nodes: Cases,     │
│  kenya_law_      │  │         Judges,    │
│  reports         │  │         Principles │
│                  │  │                    │
│  Metric: Cosine  │  │  Edges: CITES,     │
│                  │  │         OVERRULES  │
└──────────────────┘  └────────────────────┘
```

## Key Components

### 1. Document Loaders (`loaders/`)

#### PDF Loader (`pdf_loader.py`)
- Extracts text from scanned and digital PDFs
- Handles multi-page court judgments
- Preserves formatting and structure
- Uses `unstructured` library with temporary files to prevent memory overflow

#### DOCX Loader (`docx_loader.py`)
- Processes Microsoft Word documents (pleadings, legal briefs)
- Extracts text and tables
- Maintains document hierarchy

#### HTML Loader (`html_loader.py`)
- Parses Kenya Law website HTML
- Strips scripts and styling
- Preserves legal citation format

### 2. Chunking Strategy (`chunking/splitter_chunking.py`)

**Why 512 tokens?**
- Balances context preservation with embedding model capacity
- Small enough to capture specific legal concepts
- Large enough to maintain coherent legal reasoning
- Overlap of 50 tokens ensures no context loss at split points

**Legal-Specific Considerations:**
- Preserves case citations: `[Case Name] v. [Case Name] [2023] KESC 45`
- Keeps legal tests intact: "The test for adverse possession requires..."
- Maintains ratio decidendi (legal reasoning) within single chunks where possible

### 3. Embedding Generation (`embedding/embedding_compute.py`)

**Migration from Ray to Ollama:**

**Before (Ray Serve):**
```python
# Called Ray Serve endpoint
response = httpx.post("http://ray-serve-embed:8000/embed",
                     json={"text": texts, "task_type": "document"})
```

**After (Ollama):**
```python
# Calls Ollama embeddings API
response = httpx.post("http://localhost:11434/api/embeddings",
                     json={"model": "nomic-embed-text", "prompt": text})
```

**Key Differences:**
- **Ray**: Batch processing (100 chunks at once), requires GPU cluster
- **Ollama**: Sequential processing, runs locally on CPU/GPU
- **Ray**: Scalable for production (autoscaling replicas)
- **Ollama**: Simpler for development, easier debugging

**Recommended Embedding Models:**
- **nomic-embed-text**: Optimized for long-context documents (768 dimensions)
- **mxbai-embed-large**: High quality, larger model (1024 dimensions)
- **all-minilm**: Lightweight, fast (384 dimensions)

**Pull models:**
```bash
ollama pull nomic-embed-text
ollama pull mxbai-embed-large
```

### 4. Knowledge Graph Extraction (`graph/extractor_graph.py`)

**Purpose:** Extract legal entities and relationships to build a citation graph.

**Entities Extracted:**
- **Cases**: Case names, citations, courts
- **Judges**: Names, roles (e.g., "Hon. Justice [Name]")
- **Legal Principles**: Doctrines, tests, legal rules
- **Statutes**: Acts, sections, regulations

**Relationships Extracted:**
- **CITES**: Case A cites Case B
- **OVERRULES**: Case A overrules Case B
- **DISTINGUISHES**: Case A distinguishes Case B
- **APPLIES**: Case A applies principle/statute X

**Migration from Ray to Ollama:**

**Before (Ray Serve):**
```python
# OpenAI-compatible API
response = httpx.post("http://ray-serve-llm:8000/llm/chat",
                     json={"messages": [...], "temperature": 0.0})
content = response.json()["choices"][0]["message"]["content"]
```

**After (Ollama):**
```python
# Ollama chat API with JSON format enforcement
response = httpx.post("http://localhost:11434/api/chat",
                     json={
                         "model": "llama3",
                         "messages": [...],
                         "stream": False,
                         "options": {"temperature": 0.0},
                         "format": "json"  # Enforces JSON output
                     })
content = response.json()["message"]["content"]
```

**Recommended LLM Models:**
- **llama3** / **llama3.1**: Best for legal reasoning (8B or 70B)
- **qwen2.5**: Strong instruction following, good for structured output
- **mistral**: Fast, good quality

**Pull models:**
```bash
ollama pull llama3
ollama pull qwen2.5
ollama pull mistral
```

### 5. Indexing (`indexing/`)

#### Qdrant Indexing (`qdrant_indexing.py`)
- Atomic batch upserts (100 vectors at a time)
- Collection: `kenya_law_reports`
- Distance metric: Cosine similarity
- Vector dimensions: 768 (for nomic-embed-text)

#### Neo4j Indexing (`neo4j_indexing.py`)
- Idempotent Cypher queries (MERGE instead of CREATE)
- Nodes: Cases, Judges, Legal Principles, Statutes
- Relationships: CITES, OVERRULES, DISTINGUISHES, APPLIES
- Indexes on: case_name, citation, judge_name for fast lookups

## Configuration (`config.yaml`)

```yaml
embedding:
  host: http://localhost:11434      # Ollama endpoint
  model: nomic-embed-text           # Embedding model
  batch_size: 100                   # Chunks per batch

llm:
  host: http://localhost:11434      # Ollama endpoint
  model: llama3                     # LLM for graph extraction
  temperature: 0.0                  # Deterministic output
  max_tokens: 1024                  # Max generation length

vector_db:
  collection_name: kenya_law_reports
  distance_metric: Cosine
```

**Override with Environment Variables:**
```bash
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_EMBED_MODEL=nomic-embed-text
export OLLAMA_LLM_MODEL=llama3
```

## Prerequisites

### 1. Install Dependencies

```bash
# Navigate to ingestion directory
cd pipelines/ingestion

# Install Python dependencies
pip install -r requirements.txt
```

**Key dependencies:**
- `ray[data]` - Distributed data processing
- `httpx` - HTTP client for Ollama API calls
- `unstructured` - PDF parsing
- `python-docx` - DOCX parsing
- `beautifulsoup4` - HTML parsing

### 2. Configure Remote Infrastructure

This pipeline uses remote Ollama and database servers. Copy the example environment file:

```bash
# Copy environment template
cp .env.example .env

# Edit with your actual values
nano .env
```

**Infrastructure Endpoints:**

| Service | Port(s) | Access URL | Status |
|---------|---------|------------|--------|
| Ollama LLM | 11435 | http://192.168.214.22:11435 | Required |
| Ollama Embed | 11436 | http://192.168.214.22:11436 | Required |
| Qdrant API | 6333 | http://192.168.214.21:6333 | Required |
| Neo4j Bolt | 7687 | bolt://192.168.214.21:7687 | Required |
| MinIO API | 9000 | http://192.168.214.21:9000 | Required |
| Redis | 6379 | redis://192.168.214.21:6379 | Optional |
| PostgreSQL | 5432 | postgresql://192.168.214.21:5432 | Optional |

**Verify Connectivity:**
```bash
# Test Ollama LLM endpoint
curl http://192.168.214.22:11435/api/tags

# Test Ollama embedding endpoint
curl http://192.168.214.22:11436/api/tags

# Test Qdrant
curl http://192.168.214.21:6333/collections

# Test MinIO
curl http://192.168.214.21:9000/minio/health/live
```

## Running the Ingestion Pipeline

### Step 1: Test Infrastructure Connectivity

Before running the ingestion pipeline, verify all remote services are accessible:

```bash
# Run the connectivity test
python test_connection.py

# Expected output:
# ✓ Ollama LLM - PASS
# ✓ Ollama Embed - PASS
# ✓ Qdrant - PASS
# ✓ Neo4j - PASS
```

If any tests fail, check your `.env` configuration and network connectivity.

### Step 2: Set Environment Variables

```bash
# Export remote infrastructure endpoints
export OLLAMA_LLM_ENDPOINT=http://192.168.214.22:11435/api/chat
export OLLAMA_EMBED_ENDPOINT=http://192.168.214.22:11436/api/embeddings
export QDRANT_HOST=192.168.214.21
export NEO4J_URI=bolt://192.168.214.21:7687
export NEO4J_PASSWORD=your_actual_password
```

Or use the `.env` file (recommended):
```bash
# Source the environment file
set -a
source .env
set +a
```

### Step 3: Direct Python Execution

```bash
# Run ingestion for a specific MinIO bucket and prefix
python main.py <bucket_name> <prefix>

# Example: Ingest Kenya Law Reports
python main.py kenya-law-reports supreme-court/

# Example: Ingest case files
python main.py court-records-dev nairobi-high-court/
```

### Step 4: Using Test Scripts

```bash
# Upload sample data to MinIO and trigger ingestion
python ../../testExample/minio_ingestion.py

# Or use the bulk upload script
python ../../scripts/bulk_upload_s3.py
```

**Process Flow:**
1. Load documents from local directory or MinIO bucket
2. Ray Data distributes parsing across workers
3. Documents chunked into 512-token segments
4. **Fork A**: Send chunks to remote Ollama (192.168.214.22:11436) for embeddings
5. **Fork B**: Send chunks to remote Ollama (192.168.214.22:11435) for graph extraction
6. Index embeddings to Qdrant (192.168.214.21:6333)
7. Index graph data to Neo4j (192.168.214.21:7687)

## Process Flow (Step-by-Step)

### Step 1: Document Loading
```python
# Read binary files from S3/MinIO
ds = ray.data.read_binary_files(
    paths=f"s3://{bucket_name}/{prefix}",
    include_paths=True
)
```

### Step 2: Parsing & Chunking
```python
# Parse documents and chunk into 512-token segments
chunked_ds = ds.map_batches(
    process_batch,
    batch_size=10,  # 10 files per batch
    num_cpus=1
)
```

**What happens in `process_batch`:**
1. Extract text from PDF/DOCX/HTML
2. Split into 512-token chunks with 50-token overlap
3. Add metadata (filename, source, timestamp, file_type)
4. Return list of chunks

### Step 3: Parallel Processing (Fork)

**Branch A: Embedding Generation**
```python
# Generate embeddings using Ollama
vector_ds = chunked_ds.map_batches(
    BatchEmbedder,
    concurrency=5,
    batch_size=100
)
```

**What happens in `BatchEmbedder`:**
1. For each chunk, call Ollama embeddings API
2. Model: `nomic-embed-text`
3. Returns 768-dimensional vector
4. Attach vector to chunk metadata

**Branch B: Graph Extraction**
```python
# Extract entities and relationships using Ollama LLM
graph_ds = chunked_ds.map_batches(
    GraphExtractor,
    concurrency=10,
    batch_size=5
)
```

**What happens in `GraphExtractor`:**
1. Construct prompt with legal schema
2. Call Ollama LLM (`llama3`) with `format: json`
3. Parse JSON response for entities and relationships
4. Return nodes (Cases, Judges, Principles) and edges (CITES, OVERRULES)

### Step 4: Indexing

**Vector Indexing (Qdrant):**
```python
vector_ds.write_datasource(QdrantIndexer())
```
- Batch upsert to `kenya_law_reports` collection
- Each vector has: id, vector (768d), metadata (case_name, citation, court)
- Enables semantic search: "Find cases about adverse possession"

**Graph Indexing (Neo4j):**
```python
graph_ds.write_datasource(Neo4jIndexer())
```
- MERGE nodes (Cases, Judges, Principles, Statutes)
- CREATE relationships (CITES, OVERRULES, DISTINGUISHES)
- Enables citation queries: "Show all cases citing Muiruri v. Republic"

## Performance Considerations

### Ray + Ollama Hybrid Architecture

**Why keep Ray?**
- **Parallel parsing**: CPU-intensive PDF extraction benefits from distributed processing
- **Concurrency**: Process 10 documents simultaneously on different workers
- **Scalability**: Add more Ray workers for larger document batches

**Why Ollama?**
- **Local development**: No GPU cluster required
- **Cost**: Free, open-source models
- **Flexibility**: Easy to switch models (llama3 → qwen2.5)
- **Debugging**: Clear HTTP API, easy to inspect requests/responses

### Performance Benchmarks

**Single Document (10-page judgment):**
- Parsing: ~2 seconds
- Chunking: ~0.5 seconds
- Embedding (10 chunks): ~5 seconds (Ollama CPU) / ~2 seconds (Ollama GPU)
- Graph extraction: ~30 seconds (Ollama llama3-8B)
- Indexing: ~1 second
- **Total: ~40 seconds**

**Batch of 100 Documents:**
- With Ray (5 workers): ~20 minutes
- Sequential: ~60 minutes

### Optimization Tips

1. **Use GPU for Ollama:**
   ```bash
   # Ollama automatically detects and uses GPU if available
   # Verify GPU usage:
   ollama ps
   ```

2. **Increase Ray Concurrency:**
   ```python
   # In main.py, adjust concurrency based on CPU/GPU resources
   vector_ds = chunked_ds.map_batches(
       BatchEmbedder,
       concurrency=10,  # Increase if you have more resources
       batch_size=100
   )
   ```

3. **Use Faster Embedding Models:**
   ```bash
   # all-minilm is 3x faster than nomic-embed-text
   ollama pull all-minilm
   export OLLAMA_EMBED_MODEL=all-minilm
   ```

4. **Skip Graph Extraction for Speed:**
   ```python
   # In main.py, comment out graph extraction for faster ingestion
   # graph_ds.write_datasource(Neo4jIndexer())  # Disable this line
   ```

## Troubleshooting

### Issue: Remote Ollama Connection Error

**Error:**
```
httpx.ConnectError: [Errno 61] Connection refused
```

**Solution:**
```bash
# Test connectivity to remote Ollama
curl http://192.168.214.22:11435/api/tags
curl http://192.168.214.22:11436/api/tags

# Check if ports are accessible
nc -zv 192.168.214.22 11435
nc -zv 192.168.214.22 11436

# Verify environment variables are set
echo $OLLAMA_LLM_ENDPOINT
echo $OLLAMA_EMBED_ENDPOINT
```

### Issue: Network Timeout

**Error:**
```
httpx.ReadTimeout: Read operation timed out
```

**Solution:**
```bash
# Check network connectivity
ping 192.168.214.22
ping 192.168.214.21

# Test latency
time curl http://192.168.214.22:11435/api/tags

# If latency is high, increase timeout in code (already set to 120-180s)
```

### Issue: Out of Memory

**Error:**
```
RuntimeError: CUDA out of memory
```

**Solution:**
```bash
# Use smaller model
ollama pull llama3:8b  # Instead of llama3:70b

# Or use CPU
export OLLAMA_NUM_GPU=0
```

### Issue: Slow Embedding Generation

**Problem:** Ollama processes embeddings sequentially (not batched)

**Solution:**
1. **Use GPU**: Ollama automatically uses GPU if available (10x faster)
2. **Increase Ray concurrency**: More workers = more parallel Ollama calls
   ```python
   vector_ds = chunked_ds.map_batches(
       BatchEmbedder,
       concurrency=10,  # More workers
       batch_size=50    # Smaller batches
   )
   ```
3. **Use lighter model**: `all-minilm` is 3x faster than `nomic-embed-text`

### Issue: Graph Extraction Returns Empty Results

**Problem:** LLM not following JSON format

**Solution:**
1. Ensure `format: "json"` is set in Ollama API call (already done)
2. Try different model:
   ```bash
   export OLLAMA_LLM_MODEL=qwen2.5  # Better at structured output
   ```
3. Check graph extraction logs:
   ```python
   # In extractor_graph.py, errors are logged to console
   ```

### Issue: Ray Init Error

**Error:**
```
ray.exceptions.RaySystemError: System error: ray.init() called twice
```

**Solution:**
```bash
# Stop existing Ray cluster
ray stop

# Restart ingestion
python pipelines/ingestion/main.py <bucket> <prefix>
```

## Monitoring & Observability

### Check Ingestion Progress

**Qdrant Collection Stats:**
```bash
# Check number of vectors indexed
curl http://localhost:6333/collections/kenya_law_reports
```

**Neo4j Graph Stats:**
```cypher
// Open Neo4j Browser: http://localhost:7474
// Run query:
MATCH (n) RETURN labels(n), count(*)
```

### Logs

**Ray Dashboard:**
```bash
# View Ray dashboard (if Ray is running)
# URL printed when running main.py
# Example: http://127.0.0.1:8265
```

**Ollama Logs:**
```bash
# View Ollama server logs
ollama logs
```

## Migration Notes: Ray → Ollama

### What Changed

| Component | Before (Ray Serve) | After (Ollama) | Reason |
|-----------|-------------------|----------------|---------|
| Embedding | `ray-serve-embed:8000/embed` | `192.168.214.22:11436/api/embeddings` | Remote Ollama |
| LLM | `ray-serve-llm:8000/llm/chat` | `192.168.214.22:11435/api/chat` | Remote Ollama |
| Batch Size | 100 (true batch) | 1 per call (sequential) | Ollama API design |
| Deployment | Kubernetes + Ray Serve | Remote Ollama servers | Simplified testing |

### What Stayed the Same

- **Ray Data**: Still used for distributed document parsing and chunking
- **Workflow**: Same DAG (load → parse → chunk → fork → index)
- **Output**: Same vector and graph data structures
- **Indexing**: Same Qdrant and Neo4j storage

### Production Considerations

**For production scale (1000+ documents/day):**

1. **Option A: Keep Ollama + Scale Horizontally**
   - Run multiple Ollama instances behind load balancer
   - Use Ray to parallelize across instances
   - Simple, no Kubernetes required

2. **Option B: Switch back to Ray Serve**
   - Uncomment Ray Serve endpoints in config.yaml
   - Deploy vLLM + Ray on Kubernetes
   - Better for high-concurrency workloads

3. **Option C: Hybrid**
   - Use Ollama for development
   - Use Ray Serve for production
   - Code is compatible with both (just change endpoints)

## Summary of Changes for Remote Infrastructure

### Updated Components

1. **embedding_compute.py**
   - Uses `OLLAMA_EMBED_ENDPOINT` environment variable
   - Connects to remote embedding service (port 11436)
   - Timeout increased to 120 seconds for network latency

2. **extractor_graph.py**
   - Uses `OLLAMA_LLM_ENDPOINT` environment variable
   - Connects to remote LLM service (port 11435)
   - Timeout increased to 180 seconds for LLM inference

3. **qdrant_indexing.py**
   - Default host changed to `localhost` (configurable)
   - Default collection changed to `kenya_law_reports`

4. **neo4j_indexing.py**
   - Default URI changed to `bolt://localhost:7687` (configurable)

5. **main.py**
   - Added dotenv support for environment variables
   - Added Ray initialization check to prevent double init
   - Added logging configuration

6. **Configuration Files**
   - Created `.env.example` with remote endpoints
   - Updated `requirements.txt` with httpx, ray, qdrant-client, neo4j
   - Created `test_connection.py` for infrastructure testing

## Next Steps

1. **Configure Environment:**
   ```bash
   # Copy example config
   cp .env.example .env

   # Edit with your values
   nano .env
   ```

2. **Test Connectivity:**
   ```bash
   # Run connection tests
   python test_connection.py
   ```

3. **Install Dependencies:**
   ```bash
   # Install required packages
   pip install -r requirements.txt
   ```

4. **Run Ingestion:**
   ```bash
   # Set environment
   source .env

   # Run pipeline
   python main.py kenya-law-reports supreme-court/
   ```

5. **Verify Data:**
   ```bash
   # Check Qdrant vectors
   curl http://192.168.214.21:6333/collections/kenya_law_reports

   # Check Neo4j graph (open in browser)
   # http://192.168.214.21:7474
   # Run: MATCH (n) RETURN n LIMIT 25
   ```

## Additional Resources

- **Ollama Documentation**: https://ollama.com/
- **Ray Data Guide**: https://docs.ray.io/en/latest/data/overview.html
- **Qdrant Docs**: https://qdrant.tech/documentation/
- **Neo4j Cypher**: https://neo4j.com/docs/cypher-manual/current/

## Support

For issues or questions:
- GitHub Issues: https://github.com/sheria-platform/judicial-mvp/issues
- Email: dev-support@sheriaplatform.go.ke
