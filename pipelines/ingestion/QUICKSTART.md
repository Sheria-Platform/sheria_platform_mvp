# Ingestion Pipeline - Quick Start Guide

## 🚀 5-Minute Setup

### Step 1: Install Ollama

```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve
```

### Step 2: Pull Required Models

```bash
# Embedding model (required) - ~275MB
ollama pull nomic-embed-text

# LLM for graph extraction (required) - ~4.7GB
ollama pull llama3

# Verify installation
ollama list
```

### Step 3: Install Python Dependencies

```bash
cd pipelines/ingestion
pip install -r requirements.txt
```

### Step 4: Start Local Infrastructure

```bash
# From project root
make up

# This starts:
# - Qdrant (port 6333)
# - Neo4j (port 7474/7687)
# - MinIO (port 9000/9001)
# - PostgreSQL (port 5432)
# - Redis (port 6379)
```

### Step 5: Run Ingestion

```bash
# Option A: Test with sample data
python testExample/minio_ingestion.py

# Option B: Ingest from specific bucket
python pipelines/ingestion/main.py <bucket_name> <prefix>

# Example: Kenya Law Reports
python pipelines/ingestion/main.py kenya-law-reports supreme-court/
```

---

## 📋 Common Commands

### Ollama Management

```bash
# List downloaded models
ollama list

# Pull additional models
ollama pull mxbai-embed-large    # Better embeddings
ollama pull llama3.1             # Larger LLM

# Remove model to save space
ollama rm llama3

# Check Ollama status
curl http://localhost:11434/api/tags
```

### Infrastructure Management

```bash
# Start all services
make up

# Stop all services
make down

# Check service status
docker ps

# View logs
docker logs <container_name>
```

### Verify Ingestion

```bash
# Check Qdrant collection
curl http://localhost:6333/collections/kenya_law_reports

# Check Neo4j graph
# Open browser: http://localhost:7474
# Username: neo4j
# Password: password
# Query: MATCH (n) RETURN n LIMIT 25
```

---

## 🔧 Configuration

### Environment Variables

```bash
# Ollama endpoint (default: http://localhost:11434)
export OLLAMA_HOST=http://localhost:11434

# Embedding model (default: nomic-embed-text)
export OLLAMA_EMBED_MODEL=nomic-embed-text

# LLM model (default: llama3)
export OLLAMA_LLM_MODEL=llama3
```

### Config File (`config.yaml`)

```yaml
embedding:
  host: http://localhost:11434
  model: nomic-embed-text
  batch_size: 100

llm:
  host: http://localhost:11434
  model: llama3
  temperature: 0.0

vector_db:
  collection_name: kenya_law_reports
```

---

## ⚡ Performance Tips

### Use GPU (10x Faster)
```bash
# Ollama automatically uses GPU if available
# Verify GPU usage:
ollama ps
```

### Faster Embedding Model
```bash
ollama pull all-minilm  # 3x faster than nomic-embed-text
export OLLAMA_EMBED_MODEL=all-minilm
```

### Increase Parallelism
```python
# In main.py, increase concurrency:
vector_ds = chunked_ds.map_batches(
    BatchEmbedder,
    concurrency=10,  # Increase this
    batch_size=100
)
```

---

## 🐛 Troubleshooting

### Ollama Not Running
```bash
# Error: Connection refused
# Solution: Start Ollama
ollama serve
```

### Out of Memory
```bash
# Use smaller LLM
ollama pull llama3:8b  # Instead of default

# Or use CPU only
export OLLAMA_NUM_GPU=0
```

### Ray Init Error
```bash
# Error: ray.init() called twice
# Solution: Stop existing Ray cluster
ray stop
```

### Slow Processing
```bash
# Check GPU usage
ollama ps

# Use lighter models
export OLLAMA_EMBED_MODEL=all-minilm
export OLLAMA_LLM_MODEL=mistral
```

---

## 📊 Expected Performance

**Single Document (10-page judgment):**
- CPU: ~40 seconds
- GPU: ~15 seconds

**Batch of 100 Documents:**
- With Ray (5 workers): ~20 minutes
- Sequential: ~60 minutes

---

## 🎯 What Gets Indexed

### Vector Database (Qdrant)
- **Collection**: `kenya_law_reports`
- **Vectors**: 768-dimensional embeddings
- **Metadata**: case_name, citation, court, date, chunk_text
- **Use**: Semantic search ("Find cases about adverse possession")

### Graph Database (Neo4j)
- **Nodes**: Cases, Judges, Legal Principles, Statutes
- **Relationships**: CITES, OVERRULES, DISTINGUISHES, APPLIES
- **Use**: Citation queries ("Show cases citing Muiruri v. Republic")

---

## 📚 Learn More

- [Full Documentation](README.md)
- [Architecture Deep Dive](https://freedium-mirror.cfd/building-a-scalable-production-grade-agentic-rag-pipeline-1168dcd36260)
- [Ollama Docs](https://ollama.com/)
- [Qdrant Guide](https://qdrant.tech/documentation/)

---

## ✅ Checklist

- [ ] Ollama installed and running (`ollama serve`)
- [ ] Models downloaded (`ollama list`)
- [ ] Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Infrastructure running (`docker ps`)
- [ ] Test ingestion successful
- [ ] Data verified in Qdrant (`curl http://localhost:6333/collections/kenya_law_reports`)
- [ ] Graph verified in Neo4j (browser: http://localhost:7474)

---

**Ready to ingest!** 🚀

For detailed documentation, see [README.md](README.md)
