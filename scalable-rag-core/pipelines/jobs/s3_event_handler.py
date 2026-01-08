# pipelines/jobs/s3_event_handler.py
from ray.job_submission import JobSubmissionClient

def handle_s3_event(event, context):
    """Triggered by S3 Upload -> Submits Ray Job."""
    client = JobSubmissionClient("http://rag-ray-cluster-head-svc:8265")
    client.submit_job(
        entrypoint=f"python pipelines/ingestion/main.py {bucket} {key}",
        runtime_env={"working_dir": "./"}
        
    )

#TODO: Make adjustment for minio s3 server
# https://chat.deepseek.com/a/chat/s/8546beb6-9502-49a6-9e81-637ed49a939f