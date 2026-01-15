
    
import requests
import json
from langchain_ollama import OllamaEmbeddings
from langchain_ollama import OllamaLLM

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "rag_collection"
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"

print(f"✓ Connecting to Qdrant at {QDRANT_URL}")

# Step 1: Verify collection exists
try:
    resp = requests.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
    if resp.status_code == 200:
        print(f"✓ Collection '{COLLECTION_NAME}' exists")
    else:
        print(f"✗ Collection not found: {resp.status_code}")
        exit()
except Exception as e:
    print(f"Connection error: {e}")
    exit()

# Step 2: Initialize Ollama embeddings
embedder = OllamaEmbeddings(model="nomic-embed-text")
print("✓ Using Ollama embeddings for query")

# Step 3: Check available models
import subprocess
result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
print("Available Ollama models:")
print(result.stdout)

if "No such file" in result.stderr or not result.stdout.strip():
    print("\n✗ No models found. Please pull a model first:")
    print("  ollama pull mistral")
    print("  ollama pull llama2")
    print("  ollama pull neural-chat")
    exit()

# Try common models in order of preference
available_models = ["mistral", "neural-chat", "llama2", "orca-mini", "tinyllama"]
llm = None
for model in available_models:
    try:
        llm = OllamaLLM(model=model)
        print(f"✓ Initialized Ollama LLM (model: {model})")
        break
    except Exception as e:
        continue

if llm is None:
    print("\n✗ Could not initialize any model. Please pull one:")
    print("  ollama pull mistral  # Fast and good quality")
    print("  ollama pull llama2   # More capable but slower")
    exit()

# Step 4: User query
query_text = "return all judges in Agnes Ndinda Malundu v Family Bank Limited?"

# Step 5: Generate query vector
query_vector = embedder.embed_query(query_text)
print(f"✓ Generated query vector with {len(query_vector)} dimensions\n")

# Step 6: Search using REST API
try:
    search_payload = {
        "vector": query_vector,
        "limit": 5,
        "with_payload": True
    }
    
    resp = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search",
        json=search_payload
    )
    
    if resp.status_code == 200:
        results = resp.json()
        
        if results['result']:
            print(f"{'='*80}")
            print(f"SEARCH RESULTS: Found {len(results['result'])} relevant documents")
            print(f"{'='*80}\n")
            
            # Collect context from search results
            context_parts = []
            for i, hit in enumerate(results['result'], 1):
                payload = hit['payload']
                metadata = payload.get('metadata', {})
                text_snippet = payload.get('text', '')
                score = hit['score']
                filename = metadata.get('filename', 'Unknown')
                
                print(f"[Document {i}] {filename}")
                print(f"Relevance Score: {score:.2%}")
                print(f"Content:\n{text_snippet}\n")
                print("-" * 80 + "\n")
                
                # Add to context for LLM
                context_parts.append(f"Document {i} ({filename}):\n{text_snippet}")
            
            # Step 7: Generate answer using LLM with retrieved context
            print(f"{'='*80}")
            print("GENERATING ANSWER BASED ON RETRIEVED DOCUMENTS")
            print(f"{'='*80}\n")
            
            context = "\n\n".join(context_parts)
            
            prompt = f"""Based on the following case law documents, extract and provide a comprehensive list.

QUERY: {query_text}

RELEVANT CASE LAW DOCUMENTS:
{context}

INSTRUCTIONS:
1. Extract ALL judges mentioned in the documents (including their initials, titles like J, JA, CJ)
2. Extract the case name/title for each document
3. Extract the citation/reference number for each case
4. List any key legal rulings or holdings from each case
5. Format as a structured list with clear sections for each case
6. Include the document filename for reference
7. Do NOT make up or assume information - only extract what is explicitly stated
8. If a judge name is partially visible or unclear, indicate this with [unclear]

ANSWER:"""
            
            print("Generating comprehensive answer...\n")
            answer = llm.invoke(prompt)
            
            print(answer)
            print(f"\n{'='*80}")
            print("END OF ANSWER")
            print(f"{'='*80}")
            
        else:
            print("No results found in the knowledge base.")
    else:
        print(f"Search failed with status {resp.status_code}")
        print(f"Response: {resp.text}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
