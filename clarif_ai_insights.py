import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from clarifai_grpc.channel.clarifai_channel import ClarifaiChannel
from clarifai_grpc.grpc.api import service_pb2, service_pb2_grpc
from clarifai_grpc.grpc.api import resources_pb2
from clarifai_grpc.grpc.api.status import status_code_pb2
import subprocess
import os
import base64
# Import S3 utility function
from s3_utils import upload_to_s3, S3_BUCKET_NAME

# Load environment variables
load_dotenv()

# Configure Clarifai
CLARIFAI_PAT = os.getenv("CLARIFAI_PAT")
if not CLARIFAI_PAT:
    raise ValueError("CLARIFAI_PAT environment variable is not set")

# AWS Configuration is now in s3_utils.py

USER_ID = "clarifai"
APP_ID = "main"

MODEL_ID = "d16f390eb32cad478c7ae150069bd2c6"  # This is the general-video-recognition model

MODEL_USER_ID = "clarifai"
MODEL_APP_ID = "general"

EMOTION_MODEL_ID = "face-emotion-recognition"
DEMO_MODEL_ID = "demographics"
TEXT_MODEL_ID = "ocr-scene-text-detection"

channel = ClarifaiChannel.get_grpc_channel()
stub = service_pb2_grpc.V2Stub(channel)
metadata = (('authorization', 'Key ' + CLARIFAI_PAT),)

userDataObject = resources_pb2.UserAppIDSet(user_id=USER_ID, app_id=APP_ID)

# read_file_bytes is no longer needed here if only used for S3 upload before
# def read_file_bytes(filepath):
#     with open(filepath, "rb") as f:
#         return f.read()

# upload_to_s3 function is now in s3_utils.py

def extract_video_insights(video_url: str, sample_ms: int = 1000, brand_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    # Define the specific model owner and app ID - NOT needed directly in request based on docs
    # model_user_app_id = resources_pb2.UserAppIDSet(user_id=MODEL_USER_ID, app_id=MODEL_APP_ID)

    # NOTE: You might need a specific MODEL_VERSION_ID, the docs use it.
    # MODEL_VERSION_ID = 'YOUR_MODEL_VERSION_ID_HERE' # e.g., 'aa7f35c01e0642fda5cf400f543e7c40' for general-image-recognition

    request = service_pb2.PostModelOutputsRequest(
        user_app_id=userDataObject,  # User making the request
        model_id=MODEL_ID,           # Model ID specified at top level
        # version_id=MODEL_VERSION_ID, # Optional: Specify version
        inputs=[
            resources_pb2.Input(
                data=resources_pb2.Data(
                    video=resources_pb2.Video(url=video_url) # Use the S3 URL
                )
            )
        ],
        # Nested model field containing output configuration
        model=resources_pb2.Model(
            output_info=resources_pb2.OutputInfo(
                output_config=resources_pb2.OutputConfig(sample_ms=sample_ms)
            )
            # Removed id and user_app_id from here as model_id is top-level
        )
        # Removed incorrect top-level output_config
    )

    response = stub.PostModelOutputs(request, metadata=metadata)
    if response.status.code != status_code_pb2.SUCCESS:
        raise Exception("Clarifai API call failed: " + response.status.description)


    frame_data = response.outputs[0].data.frames

    insights = {
        "frames_analyzed": len(frame_data),
        "concept_frequency": {},
        "face_counts": [],
        "emotion_distribution": {},
        "dominant_colors": [],
        "brightness_levels": [],
        "demographics": [],
        "brand_appearance_timestamps": [],
        "cut_count": 0,
        "avg_time_per_cut_sec": 0.0
    }

    previous_concepts = set()
    last_timestamp = 0
    cut_timestamps = []

    for frame in frame_data:
        timestamp = frame.frame_info.time  # in milliseconds
        concept_names = []
        face_count = 0
        emotions = []
        demographics = []
        dominant_color = "unknown"
        brightness_score = 0.0

        for concept in frame.data.concepts:
            name = concept.name.lower()
            concept_names.append(name)
            insights["concept_frequency"][name] = insights["concept_frequency"].get(name, 0) + 1

            # Estimate brightness by checking for "bright", "light", "dark", etc.
            if name in ["bright", "light"]:
                brightness_score += concept.value
            elif name in ["dark"]:
                brightness_score -= concept.value

            # Detect dominant color-like concepts
            if name in ["red", "blue", "green", "yellow", "orange", "purple", "pink", "white", "black"]:
                dominant_color = name

        # Detect visual cuts: new set of concepts = possible cut
        if previous_concepts and set(concept_names) != previous_concepts:
            cut_timestamps.append(timestamp)
        previous_concepts = set(concept_names)

        # Brand detection
        if brand_keywords:
            if any(brand.lower() in concept_names for brand in brand_keywords):
                insights["brand_appearance_timestamps"].append(timestamp)

        # Placeholder for face and emotion detection count
        if hasattr(frame.data, 'regions'):
            face_count = len(frame.data.regions)
            for region in frame.data.regions:
                if region.data.face and region.data.face.emotions:
                    for emotion in region.data.face.emotions:
                        label = emotion.concept.name
                        insights["emotion_distribution"][label] = insights["emotion_distribution"].get(label, 0) + 1

                if region.data.face.demographics:
                    for attr in region.data.face.demographics:
                        if attr.concept.name in ["young adult", "teen", "adult", "senior"]:
                            demographics.append(attr.concept.name)

        insights["face_counts"].append((timestamp, face_count))
        insights["dominant_colors"].append((timestamp, dominant_color))
        insights["brightness_levels"].append((timestamp, round(brightness_score, 2)))
        for demo in demographics:
            insights["demographics"].append(demo)
        last_timestamp = timestamp

    # Calculate cut statistics
    insights["cut_count"] = len(cut_timestamps)
    if len(cut_timestamps) > 1:
        total_duration_sec = last_timestamp / 1000
        insights["avg_time_per_cut_sec"] = round(total_duration_sec / len(cut_timestamps), 2)

    return insights

def download_video_with_ytdlp(url: str, output_path: str = "temp_video.mp4") -> str:
    try:
        print(f"Downloading video from: {url}")
        # yt-dlp will auto-pick best format and save as output_path
        command = [
            "yt-dlp",
            "-f", "mp4",
            "-o", output_path,
            url
        ]
        subprocess.run(command, check=True)
        if os.path.exists(output_path):
            print(f"Downloaded to: {output_path}")
            return output_path
        else:
            raise Exception("Download failed: file not found.")
    except Exception as e:
        raise Exception(f"Video download failed: {str(e)}")

# Test run
if __name__ == "__main__":
    video_url_source = "https://www.youtube.com/shorts/U1MigIJXJx8"
    local_filename = "temp_video.mp4"
    # Use the S3 bucket name imported from s3_utils
    s3_object_key = "videos/" + os.path.basename(local_filename) # Optional: organize in S3
    local_path = None # Initialize local_path
    try:
        # 1. Download the video
        local_path = download_video_with_ytdlp(video_url_source, output_path=local_filename)

        # 2. Upload to S3 using the imported function
        s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)

        # 3. Extract Insights using S3 URL
        brand_keywords = ["tesla"] # Example keywords
        result = extract_video_insights(s3_video_url, sample_ms=1000, brand_keywords=brand_keywords)
        print("--- Video Insights ---")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(f"An error occurred: {e}")

    finally:
        # 4. Clean up the local file
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                print(f"Cleaned up local file: {local_path}")
            except OSError as e:
                print(f"Error deleting file {local_path}: {e}")

