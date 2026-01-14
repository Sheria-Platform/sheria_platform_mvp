"""
Simple MinIO Ingestion Pipeline for Kenya Law Data
Uploads files from local directory to MinIO and processes them through RAG pipeline
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from minio import Minio
from minio.error import S3Error


class MinIOConfig:
    """MinIO configuration"""
    ENDPOINT = "localhost:9000"
    ACCESS_KEY = "minioadmin"
    SECRET_KEY = "minioadmin"
    SECURE = False
    BUCKET_NAME = "kenya-law-data"
    DATA_PATH = "./kenya_law_data"


class SimpleMinIOUploader:
    """Handles file uploads to MinIO"""

    def __init__(self):
        self.config = MinIOConfig()
        self.client = Minio(
            self.config.ENDPOINT,
            access_key=self.config.ACCESS_KEY,
            secret_key=self.config.SECRET_KEY,
            secure=self.config.SECURE,
        )
        print(f"✓ Connected to MinIO at {self.config.ENDPOINT}")

    def setup_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.config.BUCKET_NAME):
                self.client.make_bucket(self.config.BUCKET_NAME)
                print(f"✓ Created bucket: {self.config.BUCKET_NAME}")
            else:
                print(f"✓ Bucket exists: {self.config.BUCKET_NAME}")
            return True
        except S3Error as e:
            print(f"✗ Error with bucket: {e}")
            return False

    def upload_file(self, file_path: Path) -> bool:
        """Upload a single file to MinIO"""
        try:
            # Create object name preserving directory structure
            relative_path = file_path.relative_to(self.config.DATA_PATH)
            object_name = str(relative_path).replace("\\", "/")

            # Upload file
            self.client.fput_object(
                self.config.BUCKET_NAME,
                object_name,
                str(file_path),
            )
            print(f"✓ Uploaded: {object_name}")
            return True

        except S3Error as e:
            print(f"✗ Failed to upload {file_path.name}: {e}")
            return False
        except Exception as e:
            print(f"✗ Error uploading {file_path.name}: {e}")
            return False

    def upload_all_files(self):
        """Upload all PDF, DOCX, and HTML files from data directory"""
        data_path = Path(self.config.DATA_PATH)

        if not data_path.exists():
            print(f"✗ Directory not found: {data_path}")
            return 0

        # Find all supported files
        supported_extensions = [".pdf", ".docx", ".html", ".txt"]
        files = []
        for ext in supported_extensions:
            files.extend(list(data_path.glob(f"**/*{ext}")))

        if not files:
            print(f"✗ No files found in {data_path}")
            return 0

        print(f"\nFound {len(files)} files to upload")
        print("-" * 60)

        # Upload each file
        success_count = 0
        for i, file_path in enumerate(files, 1):
            print(f"[{i}/{len(files)}] ", end="")
            if self.upload_file(file_path):
                success_count += 1

        print("-" * 60)
        print(f"Upload complete: {success_count}/{len(files)} successful")
        return success_count

    def list_files(self):
        """List all files in the bucket"""
        try:
            objects = self.client.list_objects(
                self.config.BUCKET_NAME, 
                recursive=True
            )
            files = [obj.object_name for obj in objects]
            
            if files:
                print(f"\nFiles in bucket '{self.config.BUCKET_NAME}':")
                for f in files:
                    print(f"  - {f}")
            else:
                print(f"Bucket '{self.config.BUCKET_NAME}' is empty")
            
            return files
        except S3Error as e:
            print(f"✗ Error listing files: {e}")
            return []


def main():
    """Main execution"""
    print("=" * 60)
    print("Simple MinIO Upload for Kenya Law Data")
    print("=" * 60)

    # Initialize uploader
    uploader = SimpleMinIOUploader()

    # Setup bucket
    if not uploader.setup_bucket():
        print("Failed to setup bucket. Exiting.")
        return

    # Upload files
    print("\nStarting upload...")
    uploaded_count = uploader.upload_all_files()

    if uploaded_count > 0:
        print("\n" + "=" * 60)
        print("✓ Upload completed successfully!")
        print("=" * 60)
        
        # List uploaded files
        uploader.list_files()
    else:
        print("\n✗ No files were uploaded")


if __name__ == "__main__":
    main()
