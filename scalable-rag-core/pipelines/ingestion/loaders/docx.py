# pipelines/ingestion/loaders/docx.py
import docx
import io

def parse_docx_bytes(file_bytes: bytes, filename: str):
    """Parses .docx files extracting text and simple tables."""
    doc = docx.Document(io.BytesIO(file_bytes))
    full_text = []
    
    for para in doc.paragraphs:
        if para.text.strip():
            full_text.append(para.text)
            
    return "\n\n".join(full_text), {"filename": filename, "type": "docx"}