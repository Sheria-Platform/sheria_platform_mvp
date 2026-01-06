# Simple RAG Project 
Database solution for the project:

1. Aurora Postgres for chat history and metadata storage.
1. Redis for caching frequently accessed data.
1. Qdrant as our vector database for storing embeddings.
1. Neo4j as our graph database for storing relationships between entities.

## Core Shared Utilities

### 1. Unique Id Generation

When a user sends a chat to our RAG bot, many things happen simultaneously, and mapping them all together helps us track issues related to that specific chat session across the various components of our RAG pipeline.

```bash
libs/utils/ids.py
```

### Measure execution time

We need to measure the execution time of various functions in our RAG pipeline for performance monitoring and optimization.

```bash
libs/utils/timing.py
```

### Retry mechanism

we need a retry mechanism and in production grade rag system we normally use exponential backoff for handling errors in our RAG pipeline.

```bash
libs/utils/backoff.py
```

we use a formula base * (2 ^ retries) + random_jitter to calculate the delay before each retry. This helps us to prevent the Thundering Herd problem where multiple clients retry at the same time.

## Data Ingestion Layer

Ray Data allows us to create a Directed Acyclic Graph (DAG) of tasks that can be executed in parallel across multiple nodes in a cluster.

### configurations

This will contain all the configuration of our ingestion pipeline

```bash
pipelines/ingestion/config.yaml
```

### pdf ingestion values

Separate pdf ingestion workflow to prevent crushing incase of failure.

```bash
pipelines/ingestion/loaders/pdf.py
```

### docx ingestion values

Ingestion word documents

```bash
pipelines/ingestion/loaders/docx.py
```

### html ingestion

Ingestion of web content.

```bash
pipelines/ingestion/loaders/html.py
```

## Chunking and Knowledge Graph

in this section the following operations will take place.

### Splitting

The splitter brakes text into 512 token chunks the standard limit for embedding.
The token token chunks can be adjusted to fit the embedding requirements.

```bash
pipelines/ingestion/chunking/splitter.py
```

### Metadata Enrichment

Its important to avoid duplication in the system. To archive we generate a content hash and add a timestamp.

```bash
pipelines/ingestion/chunking/metadata.py
```

### Batch Embedding

We call the RAy Server Endpoint. This allows our ingestion job to simply make HTTP request to a continuously running model service.

```bash
pipelines/ingestion/embedding/compute.py
```

### Graph Extractor

To keep our knowledge graph clean we need to define a strict schema this will reduce the LLM hallucinating random relation types.

```bash
pipelines/ingestion/graph/schema.py
```

This uses the LLM to understand the structure of the text, not just the semantic similarity.

```bash
pipelines/ingestion/graph/extractor.py
```


## High-Throughput indexing

