import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from collections import Counter, defaultdict
from clarifai_grpc.channel.clarifai_channel import ClarifaiChannel
from clarifai_grpc.grpc.api import service_pb2, service_pb2_grpc
from clarifai_grpc.grpc.api import resources_pb2
from clarifai_grpc.grpc.api.status import status_code_pb2
import subprocess

# Import S3 utility function
from s3_utils import upload_to_s3, S3_BUCKET_NAME

# Import Analyzers (We will create these files next)
from analyzers.concept_analyzer import analyze_concepts
from analyzers.color_analyzer import analyze_colors
from analyzers.face_analyzer import analyze_faces # This will handle detection, sentiment, demographics
from analyzers.object_analyzer import analyze_objects
from analyzers.celebrity_analyzer import analyze_celebrities
# Add imports for other analyzers as needed (e.g., moderation)


# Load environment variables
load_dotenv()

# --- Configurations ---
CLARIFAI_PAT = os.getenv("CLARIFAI_PAT")
if not CLARIFAI_PAT:
    raise ValueError("CLARIFAI_PAT environment variable is not set")

# Clarifai User/App Info (for making requests)
REQUEST_USER_ID = "clarifai" # Usually your own user ID if PAT is yours
REQUEST_APP_ID = "main"    # Usually your own app ID

# --- Model IDs & Owners ---
# Format: (Model_ID, owner_user_id, owner_app_id, [optional_version_id])
# Using model name as Model ID for standard models, and provided IDs as Version IDs.
# Verify these in Clarifai portal if issues persist.
GENERAL_RECOGNITION_MODEL = ("general-recognition", "clarifai", "main", "aaa03c23b3724a16a56b629203edc62c") # Model ID: general-recognition, Version ID: aaa03c...
# ^^^ Correction based on user info - aaa03c... is the MODEL ID, aa7f35c... is the VERSION ID
GENERAL_RECOGNITION_MODEL = ("aaa03c23b3724a16a56b629203edc62c", "clarifai", "main", "aa7f35c01e0642fda5cf400f543e7c40") 
COLOR_RECOGNITION_MODEL = ("color-recognition", "clarifai", "main", "dd9458324b4b45c2be1a7ba84d27cd04")
FACE_DETECTION_MODEL = ("face-detection", "clarifai", "main", "6dc7e46bc9124c5c8824be4822abe105")
FACE_SENTIMENT_MODEL = ("face-sentiment-recognition", "clarifai", "main", "a5d7776f0c064a41b48c3ce039049f65")
FACE_AGE_MODEL = ("age-demographics-recognition", "clarifai", "main", "fb9f10339ac14e23b8e960e74984401b")
FACE_GENDER_MODEL = ("gender-demographics-recognition", "clarifai", "main", "ff83d5baac004aafbe6b372ffa6f8227")
FACE_MULTICULTURALITY_MODEL = ("ethnicity-demographics-recognition", "clarifai", "main", "b2897edbda314615856039fb0c489796")
GENERAL_DETECTION_MODEL = ("general-image-detection", "clarifai", "main", "1580bb1932594c93b7e2e04456af7c6f")
CELEBRITY_DETECTION_MODEL = ("celebrity-face-detection", "clarifai", "main", "2ba4d0b0e53043f38dbbed49e03917b6")

# Add specific MODEL_VERSION_IDs here if needed e.g., GENERAL_RECOGNITION_MODEL = ("aaa...", "clarifai", "main", "VERSION_ID")

# --- gRPC Setup ---
channel = ClarifaiChannel.get_grpc_channel()
stub = service_pb2_grpc.V2Stub(channel)
metadata = (('authorization', 'Key ' + CLARIFAI_PAT),)
# This represents the user *making* the request
requestUserDataObject = resources_pb2.UserAppIDSet(user_id=REQUEST_USER_ID, app_id=REQUEST_APP_ID)


def _call_clarifai_model(video_url: str, model_details: tuple, sample_ms: int) -> Optional[service_pb2.MultiOutputResponse]:
    """Helper function to call a specific Clarifai model for video analysis."""
    model_id, model_user_id, model_app_id = model_details[:3]
    model_version_id = model_details[3] if len(model_details) > 3 else None # Optional version ID

    model_owner_user_app_id = resources_pb2.UserAppIDSet(user_id=model_user_id, app_id=model_app_id)

    print(f"Calling Clarifai model: {model_id} (Owner: {model_user_id}/{model_app_id}) for video: {video_url}")
    try:
        request = service_pb2.PostModelOutputsRequest(
            user_app_id=requestUserDataObject, # User API key making the call
            model_id=model_id,
            version_id=model_version_id, # Pass version if provided
            inputs=[
                resources_pb2.Input(
                    data=resources_pb2.Data(
                        video=resources_pb2.Video(url=video_url)
                    )
                )
            ],
            # The model field here specifies output config AND the owner of the model being called
            # This seems redundant if model_id is top-level, but let's try matching docs closely
            # UPDATE: Based on error messages, model_id at top level is correct.
            # The nested model object is ONLY for output_info.
            model=resources_pb2.Model(
                # id=model_id, # DO NOT include id here if model_id is top-level
                # user_app_id=model_owner_user_app_id, # DO NOT include owner here if model_id is top-level
                output_info=resources_pb2.OutputInfo(
                    output_config=resources_pb2.OutputConfig(
                        sample_ms=sample_ms
                    )
                )
            )
        )
        response = stub.PostModelOutputs(request, metadata=metadata)
        if response.status.code != status_code_pb2.SUCCESS:
            print(f"Clarifai API call failed for model {model_id}: {response.status.description}")
            return None
        print(f"Successfully received response from model: {model_id}")
        return response
    except Exception as e:
        print(f"Exception calling Clarifai model {model_id}: {e}")
        return None


def analyze_video_multi_model(video_url: str, sample_ms: int = 1000, brand_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Analyzes video using multiple Clarifai models and aggregates results."""

    all_insights = {}
    model_responses = {}

    # Dictionary mapping descriptive name to model details tuple
    models_to_call = {
        "general_recognition": GENERAL_RECOGNITION_MODEL,
        "color": COLOR_RECOGNITION_MODEL,
        "face_detection": FACE_DETECTION_MODEL,
        "face_sentiment": FACE_SENTIMENT_MODEL,
        "face_age": FACE_AGE_MODEL,
        "face_gender": FACE_GENDER_MODEL,
        "face_multiculturality": FACE_MULTICULTURALITY_MODEL,
        "general_detection": GENERAL_DETECTION_MODEL,
        "celebrity_detection": CELEBRITY_DETECTION_MODEL,
    }

    for name, model_details_tuple in models_to_call.items():
        response = _call_clarifai_model(video_url, model_details_tuple, sample_ms)
        if response:
            model_responses[name] = response

    # --- Analyze Responses ---
    # Pass raw responses to specific analyzers

    if "general_recognition" in model_responses:
        all_insights["concepts"] = analyze_concepts(model_responses["general_recognition"], brand_keywords)

    if "color" in model_responses:
        all_insights["colors"] = analyze_colors(model_responses["color"])

    # Face analysis requires results from multiple models potentially
    face_related_responses = {k: v for k, v in model_responses.items() if k.startswith("face_")}
    if face_related_responses:
         all_insights["faces"] = analyze_faces(face_related_responses) # Pass dict of relevant responses

    if "general_detection" in model_responses:
        all_insights["objects"] = analyze_objects(model_responses["general_detection"])

    if "celebrity_detection" in model_responses:
        all_insights["celebrities"] = analyze_celebrities(model_responses["celebrity_detection"])

    # --- TODO: Add Analysis for Moderation, Text (OCR), etc. ---

    # --- Calculate Overall Video Stats (Example) ---
    total_frames_analyzed = 0
    if model_responses:
        # Get frame count from the first successful response (assuming consistent frame count)
        first_successful_response = next(iter(model_responses.values()))
        if first_successful_response and first_successful_response.outputs:
             total_frames_analyzed = len(first_successful_response.outputs[0].data.frames)

    all_insights["video_summary"] = {
        "total_frames_analyzed_approx": total_frames_analyzed,
        "requested_sample_ms": sample_ms,
        "analysis_models_attempted": list(models_to_call.keys()),
        "analysis_models_succeeded": list(model_responses.keys())
    }


    return all_insights

def download_video_with_ytdlp(url: str, output_path: str = "temp_video.mp4") -> str:
    try:
        print(f"Downloading video from: {url}")
        command = ["yt-dlp", "-f", "mp4", "-o", output_path, url]
        subprocess.run(command, check=True, capture_output=True, text=True) # Added capture_output
        if os.path.exists(output_path):
            print(f"Downloaded to: {output_path}")
            return output_path
        else:
            # Check stderr if file not found
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            print(f"yt-dlp stderr: {result.stderr}")
            raise Exception("Download failed: file not found post-execution.")
    except subprocess.CalledProcessError as e:
         print(f"yt-dlp Error Output: {e.stderr}")
         raise Exception(f"Video download failed (yt-dlp error): {e}")
    except Exception as e:
        raise Exception(f"Video download failed: {str(e)}")


# --- Main Execution ---
if __name__ == "__main__":
    video_url_source = "https://www.youtube.com/shorts/DEBPsPXFww0"
    # video_url_source = "https://samples.clarifai.com/beer.mp4" # Alt test video
    local_filename = "temp_video_" + os.path.basename(video_url_source).split('?')[0] + ".mp4" # More unique name
    s3_object_key = "videos/" + local_filename
    local_path = None
    result = {}

    # Brand keywords to look for
    brand_keywords = ["cerave", "cetaphil"]

    try:
        # 1. Download
        local_path = download_video_with_ytdlp(video_url_source, output_path=local_filename)

        # 2. Upload to S3
        s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)

        # 3. Analyze using S3 URL
        print("--- Starting Multi-Model Analysis ---")
        result = analyze_video_multi_model(s3_video_url, sample_ms=125, brand_keywords=brand_keywords)  # Analyze at 8 FPS (1000ms/8 = 125ms)
        print("--- Combined Analysis Results ---")
        print(json.dumps(result, indent=2))

    except Exception as e:
        print("--- An error occurred during the process ---")
        print(f"{e}")

    finally:
        # 4. Clean up local file
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                print("Cleaned up local file: {local_path}")
            except OSError as e:
                print(f"Error deleting file {local_path}: {e}")

