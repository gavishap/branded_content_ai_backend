import os
import boto3
from botocore.exceptions import NoCredentialsError
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# AWS Configuration
S3_BUCKET_NAME = "brandedcontentai"
S3_REGION = "eu-north-1"  # Explicitly set your bucket's region

# Initialize S3 client with credentials from environment variables
s3_client = boto3.client(
    's3',
    region_name=S3_REGION,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

def upload_to_s3(local_file_path: str, bucket: str, s3_object_name: Optional[str] = None) -> str:
    """Uploads a file to an S3 bucket and returns the public URL."""
    if s3_object_name is None:
        s3_object_name = os.path.basename(local_file_path)

    try:
        print(f"Uploading {local_file_path} to s3://{bucket}/{s3_object_name} in region {S3_REGION}")
        s3_client.upload_file(
            local_file_path,
            bucket,
            s3_object_name
        )
        # Construct the public URL including the region
        s3_url = f"https://{bucket}.s3.{S3_REGION}.amazonaws.com/{s3_object_name}"
        print(f"Successfully uploaded. Access URL (requires bucket policy for public access): {s3_url}")
        return s3_url
    except FileNotFoundError:
        raise Exception(f"Error: The file {local_file_path} was not found.")
    except NoCredentialsError:
        raise Exception("Error: AWS credentials not found. Configure AWS credentials.")
    except Exception as e:
        raise Exception(f"Error uploading to S3: {str(e)}") 
