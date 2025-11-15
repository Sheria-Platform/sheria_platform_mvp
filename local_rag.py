import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()  # Optional: Loads environment variables from .env file

DATA_PATH = "data/"

# Load Documents in Python
def load_documents():
    """Loads all PDF documents from the specified data path."""
    documents = []
    pdf_files = []
    
    # Get all PDF files in the directory
    data_dir = Path(DATA_PATH)
    
    if not data_dir.exists():
        print(f"Error: Directory '{DATA_PATH}' does not exist!")
        return documents
    
    # Find all PDF files
    pdf_files = list(data_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in '{DATA_PATH}'")
        return documents
    
    print(f"Found {len(pdf_files)} PDF file(s) in '{DATA_PATH}'")
    
    # Load each PDF
    for pdf_path in pdf_files:
        try:
            loader = PyPDFLoader(str(pdf_path))
            pdf_documents = loader.load()
            documents.extend(pdf_documents)
            print(f"✓ Loaded {len(pdf_documents)} page(s) from '{pdf_path.name}'")
        except Exception as e:
            print(f"✗ Failed to load '{pdf_path.name}': {e}")
    
    print(f"\nTotal: {len(documents)} page(s) loaded from {len(pdf_files)} file(s)")
    return documents

# Split Documents into smaller chunks
def split_documents(documents):
    """Splits documents into smaller chunks."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    all_splits = text_splitter.split_documents(documents)
    print(f"Split into {len(all_splits)} chunks")
    return all_splits
# Embeddings
# Ollama Embeddings
def get_embedding_function(model_name="nomic-embed-text"):
    """Initializes the Ollama embedding function."""
    # Ensure Ollama server is running (ollama serve)
    embeddings = OllamaEmbeddings(model=model_name)
    print(f"Initialized Ollama embeddings with model: {model_name}")
    return embeddings

# Sentence Transformers
# # Alternative embedding function using Sentence Transformers
# from langchain_community.embeddings import HuggingFaceEmbeddings

# def get_embedding_function_hf(model_name="all-MiniLM-L6-v2"):
#      """Initializes HuggingFace embeddings (runs locally)."""
#      embeddings = HuggingFaceEmbeddings(model_name=model_name)
#      print(f"Initialized HuggingFace embeddings with model: {model_name}")
#      return embeddings

# embedding_function = get_embedding_function_hf() # Use this if choosing Option B


# Vectorstore Initialization
from langchain_community.vectorstores import Chroma

CHROMA_PATH = "data/chroma_db" # Directory to store ChromaDB data

def get_vector_store(embedding_function, persist_directory=CHROMA_PATH):
    """Initializes or loads the Chroma vector store."""
    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_function
    )
    print(f"Vector store initialized/loaded from: {persist_directory}")
    return vectorstore

embedding_function = get_embedding_function()
vector_store = get_vector_store(embedding_function) # Call this later

# Usage
if __name__ == "__main__":
    docs = load_documents()
    if docs:
        splits = split_documents(docs)
        