# pipelines/ingestion/loaders/pdf.py
import tempfile
from unstructured.partition.pdf import partition_pdf

def parse_pdf_bytes(file_bytes: bytes, filename: str):
    """
    Parses a PDF file stream using a temporary file for memory efficiency.
    """
    text_content = ""
    # Use disk storage instead of RAM to prevent worker crashes on large files
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_file:
        tmp_file.write(file_bytes)
        tmp_file.flush()
        
        # 'hi_res' strategy uses OCR and Layout Analysis
        elements = partition_pdf(filename=tmp_file.name, strategy="hi_res")
        
        for el in elements:
            text_content += str(el) + "\n"
    return text_content, {"filename": filename, "type": "pdf"}

if __name__ == "__main__":
    # Example usage
    with open("scalable-rag-core/test_data/sample.pdf", "rb") as f:
        file_bytes = f.read()
    text, metadata = parse_pdf_bytes(file_bytes, "sample.pdf")
    print(text)
    print(metadata)
