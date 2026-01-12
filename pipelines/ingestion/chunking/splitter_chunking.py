# pipelines/ingestion/chunking/splitter.py

from langchain_text_splitters import RecursiveCharacterTextSplitter

def split_text(text: str, chunk_size: int = 512, overlap: int = 50):
    """Splits text into overlapping chunks to preserve context at boundaries."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ".", " ", ""]
    )
    chunks = splitter.create_documents([text])
    
    # Map to dictionary format for Ray pipeline
    return [{"text": c.page_content, "metadata": {"chunk_index": i}} for i, c in enumerate(chunks)]

if __name__ == "__main__":
    # Example usage
    sample_text = (
        "This is a sample text to demonstrate the splitting functionality. "
        "It contains multiple sentences and paragraphs to ensure that the "
        "splitter works correctly. The goal is to create chunks of text that "
        "are manageable in size while retaining context through overlaps."
    )
    chunks = split_text(sample_text, chunk_size=50, overlap=10)
    for chunk in chunks:
        print(chunk)