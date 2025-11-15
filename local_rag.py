import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

load_dotenv()  # Optional: Loads environment variables from .env file

DATA_PATH = "data/"
CHROMA_PATH = "data/chroma_db"  # Directory to store ChromaDB data


def load_documents():
    """Loads all PDF documents from the specified data path."""
    documents = []
    
    # Get all PDF files in the directory
    data_dir = Path(DATA_PATH)
    
    if not data_dir.exists():
        print(f"Error: Directory '{DATA_PATH}' does not exist!")
        print(f"Creating directory: {DATA_PATH}")
        data_dir.mkdir(parents=True, exist_ok=True)
        return documents
    
    # Find all PDF files
    pdf_files = list(data_dir.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in '{DATA_PATH}'")
        print(f"Please add PDF files to the '{DATA_PATH}' directory")
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


def get_embedding_function(model_name="nomic-embed-text"):
    """Initializes the Ollama embedding function."""
    embeddings = OllamaEmbeddings(model=model_name)
    print(f"Initialized Ollama embeddings with model: {model_name}")
    return embeddings


def get_vector_store(embedding_function, persist_directory=CHROMA_PATH):
    """Initializes or loads the Chroma vector store."""
    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_function
    )
    print(f"Vector store initialized/loaded from: {persist_directory}")
    return vectorstore


def index_documents(chunks, embedding_function, persist_directory=CHROMA_PATH):
    """Indexes document chunks into the Chroma vector store."""
    if not chunks:
        print("No chunks to index!")
        return None
        
    print(f"Indexing {len(chunks)} chunks...")
    
    # Use from_documents for initial creation
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embedding_function,
        persist_directory=persist_directory
    )
    print(f"Indexing complete. Data saved to: {persist_directory}")
    return vectorstore


def create_rag_chain(vector_store, llm_model_name="qwen2.5:7b", context_window=8192):
    """Creates the RAG chain."""
    # Initialize the LLM
    llm = ChatOllama(
        model=llm_model_name,
        temperature=0,  # Lower temperature for more factual RAG answers
        num_ctx=context_window  # Set context window size
    )
    print(f"Initialized ChatOllama with model: {llm_model_name}, context window: {context_window}")

    # Create the retriever
    retriever = vector_store.as_retriever(
        search_type="similarity",  # Or "mmr"
        search_kwargs={'k': 3}  # Retrieve top 3 relevant chunks
    )
    print("Retriever initialized.")

    # Define the prompt template
    template = """Answer the question based ONLY on the following context:
{context}

Question: {question}

Answer: """
    
    prompt = ChatPromptTemplate.from_template(template)
    print("Prompt template created.")

    # Define the RAG chain using LCEL
    rag_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )
    print("RAG chain created.")
    return rag_chain


def query_rag(rag_chain, question):
    """Queries the RAG system with a question."""
    print(f"\nQuestion: {question}")
    print("-" * 80)
    response = rag_chain.invoke(question)
    print(f"Answer: {response}")
    print("-" * 80)
    return response


def setup_rag_system(force_reindex=False):
    """Sets up the complete RAG system."""
    print("=" * 80)
    print("RAG System Setup")
    print("=" * 80)
    
    # Initialize embeddings
    embedding_function = get_embedding_function()
    
    # Check if we need to index documents
    chroma_path = Path(CHROMA_PATH)
    needs_indexing = force_reindex or not chroma_path.exists()
    
    if needs_indexing:
        print("\n📚 Loading and indexing documents...")
        
        # Load documents
        docs = load_documents()
        
        if not docs:
            print("\n⚠️  No documents found. Please add PDF files to the 'data/' directory.")
            return None, None
        
        # Split documents
        chunks = split_documents(docs)
        
        # Index documents
        vector_store = index_documents(chunks, embedding_function)
    else:
        print("\n📂 Loading existing vector store...")
        vector_store = get_vector_store(embedding_function)
    
    if vector_store is None:
        print("\n❌ Failed to initialize vector store.")
        return None, None
    
    # Create RAG chain
    print("\n🔗 Creating RAG chain...")
    rag_chain = create_rag_chain(vector_store)
    
    print("\n✅ RAG system ready!")
    print("=" * 80)
    
    return rag_chain, vector_store


def interactive_mode(rag_chain):
    """Run interactive Q&A mode."""
    print("\n" + "=" * 80)
    print("Interactive Q&A Mode")
    print("=" * 80)
    print("Type your questions (or 'quit' to exit)")
    print("-" * 80)
    
    while True:
        question = input("\nYour question: ").strip()
        
        if question.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break
        
        if not question:
            continue
        
        try:
            query_rag(rag_chain, question)
        except Exception as e:
            print(f"Error: {e}")


# Usage
if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    force_reindex = "--reindex" in sys.argv
    
    # Setup RAG system
    rag_chain, vector_store = setup_rag_system(force_reindex=force_reindex)
    
    if rag_chain is None:
        print("\nFailed to setup RAG system. Exiting.")
        sys.exit(1)
    
    # Check for direct question mode
    if "--question" in sys.argv:
        idx = sys.argv.index("--question")
        if idx + 1 < len(sys.argv):
            question = sys.argv[idx + 1]
            query_rag(rag_chain, question)
        else:
            print("Error: --question requires an argument")
    else:
        # Run interactive mode
        interactive_mode(rag_chain)