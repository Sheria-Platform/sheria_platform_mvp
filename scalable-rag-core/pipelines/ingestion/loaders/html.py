# pipelines/ingestion/loaders/html.py
from bs4 import BeautifulSoup

def parse_html_bytes(file_bytes: bytes, filename: str):
    """Cleans scripts/styles from HTML to extract pure text."""
    soup = BeautifulSoup(file_bytes, "html.parser")
    
    # Remove junk elements that confuse the LLM
    for script in soup(["script", "style", "meta"]):
        script.decompose()
        
    return soup.get_text(separator="\n"), {"filename": filename, "type": "html"}