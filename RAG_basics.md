# How to Build a Local RAG System with Qwen 3

## Introduction to RAG

Retrieval-Augmented Generation (RAG) is a powerful technique that enhances Large Language Models (LLMs) by providing them with external knowledge. Instead of relying solely on training data, the LLM can retrieve relevant information from specified document sets (like local PDFs) and use that information to answer questions.

**Key Benefits:**

- Reduces "hallucinations" (incorrect or fabricated information)
- Enables answering questions about specific, private data
- No retraining required for new knowledge domains

## Core RAG Process

The RAG workflow consists of five main steps:

1. **Document Loading**: Load and parse documents from various formats
2. **Text Splitting**: Split large documents into manageable chunks
3. **Embedding Generation**: Convert text chunks into numerical representations
4. **Vector Storage**: Store embeddings in a vector database for efficient retrieval
5. **Query Processing**: Retrieve relevant context and generate informed answers

## Step 1: Load Documents in Python

Use LangChain's document loaders to read PDF content:

- **PyPDFLoader**: Simple and straightforward for basic PDFs
- **UnstructuredPDFLoader**: Handles complex layouts (requires `unstructured[pdf]` dependencies)

**Installation:**

```bash
pip install pypdf
# For UnstructuredPDFLoader:
pip install "unstructured[pdf]"
```

## Step 2: Split Documents

Large documents need to be split into smaller chunks suitable for embedding and retrieval.

**Recommended Approach:**

- Use `RecursiveCharacterTextSplitter` from LangChain
- Splits text semantically (paragraphs, sentences) before resorting to fixed-size splits

**Configuration Parameters:**

- `chunk_size`: Maximum size of each chunk (in characters)
- `chunk_overlap`: Number of characters that overlap between consecutive chunks to maintain context

**Example Configuration:**

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)
```

## Step 3: Choose and Configure Embedding Model

Embeddings transform text into vectors (numerical representations) where semantically similar text chunks have vectors that are close together in multi-dimensional space.

### Option A: Ollama Embeddings

This approach uses Ollama to serve a dedicated embedding model.

**Advantages:**

- Uses local infrastructure
- Supports various open-source embedding models

**Recommended Model:** `nomic-embed-text`

**Setup:**

```bash
# Install and run Ollama
ollama pull nomic-embed-text
```

### Option B: Sentence Transformers

This uses the `sentence-transformers` library directly within the Python script.

**Advantages:**

- No separate Ollama process required
- Direct integration with Python applications

**Installation:**

```bash
pip install sentence-transformers
```

**Model Recommendations:**

- **Fast & Lightweight**: `all-MiniLM-L6-v2`
- **Higher Quality**: `all-mpnet-base-v2`

## Step 4: Set Up Local Vector Store (ChromaDB)

ChromaDB provides an efficient way to store and search vector embeddings locally.

**Key Features:**

- Persistent storage to disk
- Fast similarity search
- Easy integration with LangChain

**Setup:**

```bash
pip install chromadb
```

**Usage Benefits:**

- Indexed data persists between sessions
- No need to re-process documents on restart
- Efficient retrieval of similar vectors

## Step 5: Query Processing and Generation

When a query is received:

1. Embed the query using the same embedding model
2. Search the vector database for the most similar document chunks
3. Provide these relevant chunks as context along with the original query
4. The LLM generates an informed answer using the retrieved context

## Implementation Considerations

- **Chunk Size**: Balance between context preservation and retrieval accuracy
- **Embedding Model**: Choose based on quality requirements and computational resources
- **Vector Database**: Ensure persistence for production use
- **Performance**: Monitor retrieval times and accuracy for optimization

## Next Steps

After setting up the basic RAG pipeline, consider:

- Adding metadata filtering for more precise retrieval
- Implementing hybrid search (vector + keyword)
- Setting up evaluation metrics for retrieval quality
- Scaling to handle larger document collections
