import os
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import json

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

def download_json_from_s3(bucket: str, s3_object_key: str) -> Optional[Dict[str, Any]]:
    """Downloads a JSON file from S3 and parses it into a dictionary."""
    try:
        print(f"Attempting to download JSON from s3://{bucket}/{s3_object_key}")
        response = s3_client.get_object(Bucket=bucket, Key=s3_object_key)
        # Read the content as bytes and decode to string
        content_string = response['Body'].read().decode('utf-8')
        # Parse the JSON string into a dictionary
        data = json.loads(content_string)
        print(f"Successfully downloaded and parsed JSON from s3://{bucket}/{s3_object_key}")
        return data
    except ClientError as e:
        # Check if the error is because the object doesn't exist
        if e.response['Error']['Code'] == 'NoSuchKey':
            print(f"JSON object not found at s3://{bucket}/{s3_object_key}")
            return None
        else:
            # Re-raise other client errors (like permissions)
            print(f"AWS ClientError downloading JSON from S3: {str(e)}")
            raise
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON downloaded from s3://{bucket}/{s3_object_key}: {str(e)}")
        # Return None or raise an error depending on desired behavior
        return None
    except Exception as e:
        print(f"General error downloading JSON from S3: {str(e)}")
        raise 
