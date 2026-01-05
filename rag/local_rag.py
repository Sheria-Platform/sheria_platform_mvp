import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import time

load_dotenv()  # Optional: Loads environment variables from .env file

# Local file paths
DATA_PATH = "data/source"
CHROMA_PATH = "data/chroma_db" 


def load_documents():
    """
    Loads all PDF documents from the configured data directory.
    
    This function scans the DATA_PATH directory for PDF files, loads each file
    using PyPDFLoader, and returns a list of all loaded document pages. If the
    directory doesn't exist, it will be created automatically. The function
    provides detailed console output about the loading process, including success
    and failure messages for each file.
    
    Returns:
        list: A list of loaded document objects, where each object represents a
              page from the PDF files. Returns an empty list if no PDF files are
              found or if the directory doesn't exist and is newly created.
    """
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
    """
    Splits documents into smaller chunks for efficient processing and embedding.
    
    This function takes a list of documents and splits them into smaller, overlapping
    chunks using a recursive character-based text splitter. The splitting strategy
    ensures that each chunk is approximately 1000 characters with a 200-character
    overlap between consecutive chunks to maintain context continuity. This is
    particularly useful for vector embedding and retrieval operations where smaller,
    manageable text segments are needed.
    
    Args:
        documents (list): A list of document objects to be split. Each document
                         should be a LangChain document object with text content
                         that can be processed by the text splitter.
    
    Returns:
        list: A list of document chunks, where each chunk is a document object
              containing a portion of the original text. The function also prints
              the total number of chunks created to the console.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )
    all_splits = text_splitter.split_documents(documents)
    print(f"Split into {len(all_splits)} chunks")
    return all_splits


def get_embedding_function(model_name="bge-m3", base_url="http://localhost:11434"):
    """
    Initializes and returns an Ollama embedding function for text vectorization.
    
    This function creates an OllamaEmbeddings instance configured with the specified
    model and base URL. It performs a test embedding operation to verify that the
    model is properly loaded and functioning. The embedding function is essential
    for converting text into numerical vectors that can be stored and searched in
    the vector database.
    
    Args:
        model_name (str, optional): The name of the Ollama embedding model to use.
                                   Defaults to "nomic-embed-text". Other options
                                   include "mxbai-embed-large" or any other compatible
                                   Ollama embedding model.
        base_url (str, optional): The base URL where the Ollama service is running.
                                 Defaults to "http://localhost:11434", which is the
                                 standard local Ollama endpoint.
    
    Returns:
        OllamaEmbeddings: A configured embedding function object that can be used
                         to generate vector embeddings for text. The object includes
                         methods like embed_query() and embed_documents().
    
    Raises:
        Exception: If the embedding model cannot be initialized or if the test
                  embedding fails. The exception includes troubleshooting guidance
                  for common issues such as ensuring Ollama is running and the
                  model is properly installed.
    """
    try:
        embeddings = OllamaEmbeddings(
            model=model_name,
            base_url=base_url
        )
        
        # Test the embedding function with a simple query
        print(f"Testing embedding model '{model_name}'...")
        test_embedding = embeddings.embed_query("test")
        print(f"✓ Embedding model working (dimension: {len(test_embedding)})")
        
        return embeddings
    except Exception as e:
        print(f"✗ Error initializing embeddings: {e}")
        print(f"\nTroubleshooting:")
        print(f"1. Make sure Ollama is running: ollama list")
        print(f"2. Pull the embedding model: ollama pull {model_name}")
        print(f"3. Try alternative models: nomic-embed-text, mxbai-embed-large")
        raise


def get_vector_store(embedding_function, persist_directory=CHROMA_PATH):
    """
    Initializes or loads an existing Chroma vector store for document retrieval.
    
    This function creates a new Chroma vector store instance or loads an existing
    one from the specified directory. The vector store is used to store and retrieve
    document embeddings for similarity search operations. If a vector store already
    exists at the persist_directory, it will be loaded with all previously indexed
    documents. Otherwise, a new empty vector store will be created.
    
    Args:
        embedding_function (OllamaEmbeddings): The embedding function object used to
                                               convert text into vector representations.
                                               This should be an initialized instance
                                               of OllamaEmbeddings or compatible embedding
                                               function that provides embed_query() and
                                               embed_documents() methods.
        persist_directory (str, optional): The file system path where the vector store
                                          data will be persisted. Defaults to CHROMA_PATH
                                          constant. The directory will be created if it
                                          doesn't exist.
    
    Returns:
        Chroma: A Chroma vector store instance configured with the provided embedding
               function and persistence directory. This object can be used for adding
               documents, performing similarity searches, and creating retrievers for
               RAG applications.
    """
    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_function
    )
    print(f"Vector store initialized/loaded from: {persist_directory}")
    return vectorstore


def index_documents(chunks, embedding_function, persist_directory=CHROMA_PATH, batch_size=10):
    """
    Indexes document chunks into a Chroma vector store using batch processing.
    
    This function creates a new Chroma vector store and populates it with document
    chunks by processing them in batches. Batch processing prevents overwhelming
    the Ollama embedding service and provides better error handling. Each chunk is
    converted to a vector embedding and stored in the persistent vector database.
    The function includes progress tracking, error recovery for individual batches,
    and automatic delays between batches to ensure stable processing.
    
    Args:
        chunks (list): A list of document chunk objects to be indexed. Each chunk
                      should be a LangChain document object containing text content
                      and metadata. If the list is empty, the function returns None
                      without creating a vector store.
        embedding_function (OllamaEmbeddings): The embedding function object used to
                                               convert text chunks into vector embeddings.
                                               This should be an initialized instance of
                                               OllamaEmbeddings or compatible embedding
                                               function.
        persist_directory (str, optional): The file system path where the vector store
                                          data will be persisted. Defaults to CHROMA_PATH
                                          constant. The directory will be created if it
                                          doesn't exist.
        batch_size (int, optional): The number of chunks to process in each batch.
                                   Defaults to 10. Smaller batch sizes are more stable
                                   but slower, while larger batches are faster but may
                                   overwhelm the embedding service.
    
    Returns:
        Chroma or None: Returns a Chroma vector store instance containing all successfully
                       indexed document chunks. Returns None if the chunks list is empty.
                       The vector store can be used immediately for similarity searches
                       and retrieval operations.
    
    Raises:
        Exception: If a critical error occurs during vector store creation or if the
                  indexing process fails completely. Individual batch errors are caught
                  and logged, allowing the process to continue with remaining batches.
    """
    if not chunks:
        print("No chunks to index!")
        return None
        
    print(f"Indexing {len(chunks)} chunks in batches of {batch_size}...")
    
    try:
        # Create the vector store first
        vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=embedding_function
        )
        
        # Add documents in batches to avoid overwhelming Ollama
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(chunks) + batch_size - 1) // batch_size
            
            print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
            
            try:
                vectorstore.add_documents(batch)
                time.sleep(0.5)  # Small delay between batches
            except Exception as e:
                print(f"✗ Error processing batch {batch_num}: {e}")
                print("Continuing with next batch...")
                continue
        
        print(f"✓ Indexing complete. Data saved to: {persist_directory}")
        return vectorstore
        
    except Exception as e:
        print(f"✗ Error during indexing: {e}")
        raise


def create_rag_chain(vector_store, llm_model_name="qwen3:30b-a3b", context_window=8192):
    """
    Creates a complete RAG (Retrieval-Augmented Generation) chain for question answering.
    
    This function constructs a RAG pipeline by combining a vector store retriever, a language
    model, and a prompt template using LangChain Expression Language (LCEL). The resulting
    chain retrieves relevant document chunks from the vector store, formats them with the
    user's question into a prompt, passes the prompt to the LLM for generation, and returns
    the parsed string response. The chain is configured with a low temperature for factual
    answers and retrieves the top 3 most similar document chunks for context.
    
    Args:
        vector_store (Chroma): A Chroma vector store instance containing indexed document
                              embeddings. This vector store is used to create a retriever
                              that finds relevant document chunks based on similarity search.
        llm_model_name (str, optional): The name of the Ollama language model to use for
                                       generating answers. Defaults to "qwen3:30b-a3b".
                                       Other compatible Ollama models can be specified
                                       based on availability and requirements.
        context_window (int, optional): The maximum context window size (in tokens) for
                                       the language model. Defaults to 8192. This determines
                                       how much text (including retrieved context and the
                                       question) the model can process in a single request.
    
    Returns:
        RunnableSequence: A LangChain LCEL (LangChain Expression Language) chain 
                         that can be invoked with a question  string.
                         The chain performs retrieval, prompt formatting, LLM generation,
                         and output parsing in sequence. When invoked with a question, it
                         returns a string containing the generated answer based on the
                         retrieved context.
    """
    # Initialize the LLM
    llm = ChatOllama(
        model=llm_model_name,
        temperature=0,  # Lower temperature for more factual RAG answers
        num_ctx=context_window  # Set context window size
    )
    print(f"Initialized ChatOllama with model: {llm_model_name}, context window: {context_window}")

    # Create the retriever
    retriever = vector_store.as_retriever(
        search_type="similarity_score_threshold",  # Or "mmr"
        search_kwargs={'k': 3, 'score_threshold': 0.5}  # Retrieve top 3 relevant chunks
    )
    print("Retriever initialized.")

    # Define the prompt template
    template ="""
    You are an AI assistant that answers questions based ONLY on the provided context.
    
    Context information:
    {context}
    
    Instruction: 
    - If the context doesn't contain relevant information to answer the question, say "I cannot answer based on the provided context."
    - If the question is ambiguous, ask for clarification.
    - Provide concise, accurate answers with references to the context when possible.
    
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
    """
    Executes a question against the RAG chain and displays the formatted response.
    
    This function takes a user's question, passes it through the RAG (Retrieval-Augmented
    Generation) chain for processing, and displays both the question and the generated
    answer in a formatted console output. The RAG chain handles document retrieval,
    context formatting, LLM generation, and response parsing internally. The function
    provides visual separators for improved readability of the Q&A interaction.
    
    Args:
        rag_chain (RunnableSequence): A LangChain LCEL (LangChain Expression Language) chain that processes questions
                                     through retrieval, prompt formatting, LLM generation,
                                     and output parsing. This should be a chain created
                                     by the create_rag_chain() function.
        question (str): The user's question or query to be answered. This string is
                       passed to the RAG chain for processing and will be displayed
                       in the console output along with the generated answer.
    
    Returns:
        str: The generated answer from the RAG chain as a string. This response is
            based on the retrieved document context and the language model's generation.
            The same response is also printed to the console with formatting.
    """
    print(f"\nQuestion: {question}")
    print("-" * 80)
    response = rag_chain.invoke(question)
    print(f"Answer: {response}")
    print("-" * 80)
    return response


def setup_rag_system(force_reindex=False):
    """
    Initializes and configures the complete RAG (Retrieval-Augmented Generation) system.
    
    This function orchestrates the entire RAG system setup process by initializing the
    embedding function, managing the vector store (either loading an existing one or
    creating a new one by indexing documents), and creating the RAG chain for question
    answering. The function handles the complete workflow including document loading,
    chunking, indexing, and chain creation. It provides detailed console output for
    each step and handles errors gracefully by returning None values if any critical
    step fails.
    
    Args:
        force_reindex (bool, optional): If True, forces reindexing of all documents
                                       even if a vector store already exists. If False,
                                       the function will load the existing vector store
                                       if available. Defaults to False. This is useful
                                       when documents have been updated or when you want
                                       to rebuild the index with different parameters.
    
    Returns:
        tuple: A tuple containing two elements:
            - rag_chain (RunnableSequence or None): The configured RAG chain ready for
              question answering, or None if setup failed at any step.
            - vector_store (Chroma or None): The initialized or loaded Chroma vector
              store containing document embeddings, or None if setup failed at any step.
    """
    print("=" * 80)
    print("RAG System Setup")
    print("=" * 80)
    
    # Initialize embeddings
    try:
        embedding_function = get_embedding_function()
    except Exception as e:
        print(f"\n❌ Failed to initialize embeddings: {e}")
        return None, None
    
    # Check if we need to index documents
    chroma_path = Path(CHROMA_PATH)
    needs_indexing = force_reindex or not chroma_path.exists()
    
    if needs_indexing:
        print("\n📚 Loading and indexing documents...")
        
        # Load documents
        docs = load_documents()
        
        if not docs:
            print("\n⚠️  No documents found. Please add PDF files to the 'data/source' directory.")
            return None, None
        
        # Split documents
        chunks = split_documents(docs)
        
        # Index documents
        try:
            vector_store = index_documents(chunks, embedding_function)
        except Exception as e:
            print(f"\n❌ Failed to index documents: {e}")
            return None, None
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
    """
    Runs an interactive command-line interface for continuous question answering.
    
    This function provides a user-friendly interactive loop where users can ask
    multiple questions to the RAG system without restarting the program. The function
    displays a formatted header, continuously prompts for user input, processes each
    question through the RAG chain, and handles errors gracefully. Users can exit
    the interactive session by typing 'quit', 'exit', or 'q'. Empty questions are
    ignored, and any errors during question processing are caught and displayed
    without terminating the session.
    
    Args:
        rag_chain (RunnableSequence): A configured LangChain LCEL (LangChain Expression Language) chain that processes
                                     questions through retrieval, prompt formatting, LLM
                                     generation, and output parsing. This should be a
                                     chain created by the create_rag_chain() function
                                     and is used to generate answers for each user question.
    
    Returns:
        None: This function does not return a value. It runs until the user explicitly
             exits by entering a quit command ('quit', 'exit', or 'q'). The function
             handles all user interaction through console input/output.
    """
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