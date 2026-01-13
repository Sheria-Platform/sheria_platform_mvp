"""
Kenya Law Data - MinIO Upload and Ingestion Pipeline
This script handles:
1. Loading files from kenya_law_data folder
2. Uploading to MinIO (S3-compatible storage)
3. Ingesting files through the RAG pipeline
"""

import os
from datetime import datetime
from pathlib import Path

import ray
from minio import Minio
from minio.error import S3Error


# Configuration
class Config:
    # MinIO Settings
    MINIO_ENDPOINT = "localhost:9000"
    MINIO_ACCESS_KEY = "minioadmin"
    MINIO_SECRET_KEY = "minioadmin"
    MINIO_SECURE = False

    # Buckets
    DEV_BUCKET = "rag-dev-kenya-law"
    TRAINING_BUCKET = "rag-training-kenya-law"

    # Local data path
    DATA_PATH = "./kenya_law_data"

    # Supported file types
    SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".html", ".txt"]


class MinIOUploader:
    """Handles file uploads to MinIO"""

    def __init__(self, config: Config):
        self.config = config
        self.client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
        )

    def create_buckets(self):
        """Create dev and training buckets if they don't exist"""
        for bucket in [self.config.DEV_BUCKET, self.config.TRAINING_BUCKET]:
            try:
                if not self.client.bucket_exists(bucket):
                    self.client.make_bucket(bucket)
                    print(f"✓ Created bucket: {bucket}")
                else:
                    print(f"✓ Bucket already exists: {bucket}")
            except S3Error as e:
                print(f"✗ Error creating bucket {bucket}: {e}")

    def upload_file(self, file_path: Path, bucket_name: str, object_name: str = None):
        """Upload a single file to MinIO"""
        if object_name is None:
            object_name = file_path.name

        try:
            self.client.fput_object(
                bucket_name,
                object_name,
                str(file_path),
                metadata={
                    "upload_date": datetime.now().isoformat(),
                    "source": "kenya_law_data",
                    "file_type": file_path.suffix,
                },
            )
            print(f"✓ Uploaded: {object_name} to {bucket_name}")
            return True
        except S3Error as e:
            print(f"✗ Error uploading {file_path}: {e}")
            return False

    def upload_directory(self, bucket_name: str, split_ratio: float = 0.8):
        """
        Upload all files from kenya_law_data directory

        Args:
            bucket_name: Target bucket (dev or training)
            split_ratio: Ratio for train/dev split (0.8 = 80% training, 20% dev)
        """
        data_path = Path(self.config.DATA_PATH)

        if not data_path.exists():
            print(f"✗ Directory not found: {data_path}")
            return []

        # Get all supported files
        files = []
        for ext in self.config.SUPPORTED_EXTENSIONS:
            files.extend(list(data_path.glob(f"**/*{ext}")))

        if not files:
            print(f"✗ No files found in {data_path}")
            return []

        print(f"Found {len(files)} files to upload")

        # Split files for dev/training if needed
        if bucket_name == self.config.TRAINING_BUCKET:
            split_idx = int(len(files) * split_ratio)
            files = files[:split_idx]
            print(f"Using {len(files)} files for training ({split_ratio*100}%)")
        elif bucket_name == self.config.DEV_BUCKET:
            split_idx = int(len(files) * split_ratio)
            files = files[split_idx:]
            print(f"Using {len(files)} files for development ({(1-split_ratio)*100}%)")

        uploaded = []
        for file_path in files:
            # Create object name with relative path structure
            relative_path = file_path.relative_to(data_path)
            object_name = str(relative_path)

            if self.upload_file(file_path, bucket_name, object_name):
                uploaded.append(object_name)

        return uploaded

    def list_bucket_files(self, bucket_name: str) -> list[str]:
        """List all files in a bucket"""
        try:
            objects = self.client.list_objects(bucket_name, recursive=True)
            return [obj.object_name for obj in objects]
        except S3Error as e:
            print(f"✗ Error listing bucket {bucket_name}: {e}")
            return []


class RAGIngestionPipeline:
    """Handles ingestion of files from MinIO into RAG system"""

    def __init__(self, config: Config):
        self.config = config
        self.minio_client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
        )

    @ray.remote
    def process_document(self, bucket_name: str, object_name: str) -> dict:
        """
        Process a single document through the RAG pipeline
        This is a Ray remote function for parallel processing
        """
        from pipelines.ingestion.chunking.metadata import enrich_metadata
        from pipelines.ingestion.chunking.splitter import split_text
        from pipelines.ingestion.embedding.compute import compute_embeddings
        from pipelines.ingestion.graph.extractor import extract_graph
        from pipelines.ingestion.loaders import docx, html, pdf

        # Download file from MinIO
        temp_path = f"/tmp/{object_name}"
        os.makedirs(os.path.dirname(temp_path), exist_ok=True)

        try:
            self.minio_client.fget_object(bucket_name, object_name, temp_path)
        except S3Error as e:
            return {"status": "error", "file": object_name, "error": str(e)}

        # Load document based on file type
        file_ext = Path(object_name).suffix.lower()

        try:
            if file_ext == ".pdf":
                content = pdf.load_pdf(temp_path)
            elif file_ext == ".docx":
                content = docx.load_docx(temp_path)
            elif file_ext in [".html", ".htm"]:
                content = html.load_html(temp_path)
            else:
                content = open(temp_path, encoding="utf-8").read()

            # Process through pipeline
            chunks = split_text(content)
            enriched_chunks = enrich_metadata(chunks, source=object_name)
            embeddings = compute_embeddings(enriched_chunks)
            graph_data = extract_graph(enriched_chunks)

            # Clean up
            os.remove(temp_path)

            return {
                "status": "success",
                "file": object_name,
                "chunks": len(chunks),
                "embeddings": len(embeddings),
                "entities": len(graph_data.get("entities", [])),
            }

        except Exception as e:
            return {"status": "error", "file": object_name, "error": str(e)}

    def ingest_bucket(self, bucket_name: str, mode: str = "dev"):
        """
        Ingest all files from a MinIO bucket

        Args:
            bucket_name: Source bucket name
            mode: 'dev' or 'training' - affects processing parameters
        """
        print(f"\n{'='*60}")
        print(f"Starting ingestion from bucket: {bucket_name}")
        print(f"Mode: {mode}")
        print(f"{'='*60}\n")

        # Initialize Ray
        if not ray.is_initialized():
            ray.init()

        # Get all files from bucket
        try:
            objects = self.minio_client.list_objects(bucket_name, recursive=True)
            files = [obj.object_name for obj in objects]
        except S3Error as e:
            print(f"✗ Error listing bucket: {e}")
            return

        if not files:
            print(f"✗ No files found in bucket: {bucket_name}")
            return

        print(f"Found {len(files)} files to process")

        # Process files in parallel using Ray
        futures = []
        for file in files:
            future = self.process_document.remote(self, bucket_name, file)
            futures.append(future)

        # Wait for all processing to complete
        results = ray.get(futures)

        # Print summary
        print(f"\n{'='*60}")
        print("Ingestion Summary")
        print(f"{'='*60}")

        success_count = sum(1 for r in results if r["status"] == "success")
        error_count = sum(1 for r in results if r["status"] == "error")

        print(f"Total files: {len(results)}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")

        # Print details for successful files
        if success_count > 0:
            print("\nSuccessful ingestions:")
            for r in results:
                if r["status"] == "success":
                    print(
                        f"  ✓ {r['file']}: {r['chunks']} chunks, {r['embeddings']} embeddings, {r['entities']} entities"
                    )

        # Print errors
        if error_count > 0:
            print("\nErrors:")
            for r in results:
                if r["status"] == "error":
                    print(f"  ✗ {r['file']}: {r['error']}")

        ray.shutdown()


def main():
    """Main execution flow"""
    config = Config()

    print("=" * 60)
    print("Kenya Law Data - MinIO Upload & Ingestion Pipeline")
    print("=" * 60)

    # Step 1: Initialize MinIO uploader
    print("\n[1/4] Initializing MinIO connection...")
    uploader = MinIOUploader(config)

    # Step 2: Create buckets
    print("\n[2/4] Creating buckets...")
    uploader.create_buckets()

    # Step 3: Upload files
    print("\n[3/4] Uploading files...")

    # Upload training data (80%)
    print("\n>> Uploading TRAINING data...")
    training_files = uploader.upload_directory(config.TRAINING_BUCKET, split_ratio=0.8)

    # Upload dev data (20%)
    print("\n>> Uploading DEV data...")
    dev_files = uploader.upload_directory(config.DEV_BUCKET, split_ratio=0.8)

    print(f"\nUpload Summary:")
    print(f"  Training files: {len(training_files)}")
    print(f"  Dev files: {len(dev_files)}")

    # Step 4: Ingest data
    print("\n[4/4] Starting ingestion pipeline...")
    pipeline = RAGIngestionPipeline(config)

    # Ingest dev data first (smaller dataset)
    pipeline.ingest_bucket(config.DEV_BUCKET, mode="dev")

    # Ingest training data
    pipeline.ingest_bucket(config.TRAINING_BUCKET, mode="training")

    print("\n" + "=" * 60)
    print("✓ Pipeline completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
