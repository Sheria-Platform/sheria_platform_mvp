#!/usr/bin/env python3
"""Quick test of PDF parsing"""

import sys

sys.path.insert(0, "/Users/danielmalungu/Documents/sheria_platform_mvp")

from minio import Minio

from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes

# Connect to MinIO
client = Minio(
    "192.168.214.21:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

# List first file
objects = list(
    client.list_objects("srtmanager", prefix="kenya_law_data/case/", recursive=True)
)
if not objects:
    print("No files found!")
    sys.exit(1)

first_file = objects[0]
print(f"Testing with: {first_file.object_name}")

# Download and parse
response = client.get_object("srtmanager", first_file.object_name)
file_bytes = response.read()
response.close()

print(f"Downloaded {len(file_bytes)} bytes")

# Parse
try:
    text, metadata = parse_pdf_bytes(file_bytes, first_file.object_name)
    print(f"✓ Parsed successfully!")
    print(f"  Text length: {len(text)} chars")
    print(f"  Metadata: {metadata}")
    print(f"  First 200 chars: {text[:200]}")
except Exception as e:
    print(f"✗ Parse failed: {e}")
    import traceback

    traceback.print_exc()
