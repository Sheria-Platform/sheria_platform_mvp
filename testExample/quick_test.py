"""
Quick Start Script - Run Complete Ingestion Workflow
1. Upload files to MinIO
2. Process them through RAG pipeline
"""

import subprocess
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_services():
    """Check if required services are running"""
    print("=" * 70)
    
    print("CHECKING SERVICES")
    print("=" * 70)
    
    services = {
        'MinIO': ('localhost', 9000),
        'Qdrant': ('localhost', 6333),
        'Neo4j': ('localhost', 7687),
    }
    
    import socket
    
    all_running = True
    for service, (host, port) in services.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()
            
            if result == 0:
                print(f"✓ {service} is running on port {port}")
            else:
                print(f"✗ {service} is NOT running on port {port}")
                all_running = False
        except Exception as e:
            print(f"✗ {service} check failed: {e}")
            all_running = False
    
    if not all_running:
        print("\n⚠ Some services are not running. Start them with:")
        print("  docker-compose up -d")
        return False
    
    print("\n✓ All services are running!")
    return True


def run_upload():
    """Run MinIO upload script"""
    print("\n" + "=" * 70)
    print("STEP 1: UPLOADING FILES TO MINIO")
    print("=" * 70 + "\n")
    
    try:
        subprocess.run(
            [sys.executable, "minio_ingestion_simple.py"],
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Upload failed: {e}")
        return False


def run_ingestion(limit: int = None):
    """Run ingestion pipeline"""
    print("\n" + "=" * 70)
    print("STEP 2: PROCESSING FILES THROUGH RAG PIPELINE")
    print("=" * 70 + "\n")
    
    cmd = [sys.executable, "dev_ingestion_pipeline.py"]
    
    if limit:
        cmd.extend(["--limit", str(limit)])
    
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Ingestion failed: {e}")
        return False


def main():
    """Main workflow"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Quick start script for Kenya Law data ingestion'
    )
    parser.add_argument(
        '--skip-upload',
        action='store_true',
        help='Skip upload step (files already in MinIO)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of files to process (for testing)',
        default=None
    )
    parser.add_argument(
        '--skip-check',
        action='store_true',
        help='Skip service health check'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("KENYA LAW DATA - COMPLETE INGESTION WORKFLOW")
    print("=" * 70)
    
    # Check services
    if not args.skip_check:
        if not check_services():
            print("\n✗ Please start required services first")
            sys.exit(1)
    
    # Upload files
    if not args.skip_upload:
        if not run_upload():
            print("\n✗ Workflow failed at upload stage")
            sys.exit(1)
    else:
        print("\n⏭  Skipping upload (using existing files in MinIO)")
    
    # Run ingestion
    if not run_ingestion(limit=args.limit):
        print("\n✗ Workflow failed at ingestion stage")
        sys.exit(1)
    
    # Success
    print("\n" + "=" * 70)
    print("✓ COMPLETE WORKFLOW FINISHED SUCCESSFULLY!")
    print("=" * 70)
    print("\nYour Kenya Law data is now indexed and ready to use!")
    print("\nNext steps:")
    print("  1. Start the API: python services/api/main.py")
    print("  2. Test queries via the chat endpoint")
    print("  3. Check Qdrant dashboard: http://localhost:6333/dashboard")
    print("  4. Check Neo4j browser: http://localhost:7474")


if __name__ == "__main__":
    main()

