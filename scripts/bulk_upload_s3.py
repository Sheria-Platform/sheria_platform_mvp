# scripts/bulk_upload_s3.py
from concurrent.futures import ThreadPoolExecutor

def upload_directory(dir_path, bucket_name):
    """High-performance multi-threaded S3 uploader."""
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Maps local files to S3 upload tasks
        executor.map(upload_file, files_to_upload)