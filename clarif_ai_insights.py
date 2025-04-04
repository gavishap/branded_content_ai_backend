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
import concurrent.futures
from functools import partial

# Import S3 utility function
from s3_utils import upload_to_s3, S3_BUCKET_NAME

# Import Analyzers
from analyzers.concept_analyzer import analyze_concepts
from analyzers.face_analyzer import analyze_faces
from analyzers.object_analyzer import analyze_objects
from analyzers.celebrity_analyzer import analyze_celebrities

# Import Analysis Layers
from inference_layer import analyze_video_output
from structured_analysis import process_analysis

# Load environment variables
load_dotenv()

# --- Configurations ---
CLARIFAI_PAT = os.getenv("CLARIFAI_PAT")
if not CLARIFAI_PAT:
    raise ValueError("CLARIFAI_PAT environment variable is not set")

# Clarifai User/App Info (for making requests)
REQUEST_USER_ID = "clarifai"
REQUEST_APP_ID = "main"

# --- Model IDs & Owners ---
# Format: (model_id, owner_user_id, owner_app_id, [optional_version_id])
GENERAL_RECOGNITION_MODEL = ("aaa03c23b3724a16a56b629203edc62c", "clarifai", "main", "aa7f35c01e0642fda5cf400f543e7c40") 
FACE_DETECTION_MODEL = ("face-detection", "clarifai", "main", "6dc7e46bc9124c5c8824be4822abe105")
FACE_SENTIMENT_MODEL = ("face-sentiment-recognition", "clarifai", "main", "a5d7776f0c064a41b48c3ce039049f65")
FACE_AGE_MODEL = ("age-demographics-recognition", "clarifai", "main", "fb9f10339ac14e23b8e960e74984401b")
FACE_GENDER_MODEL = ("gender-demographics-recognition", "clarifai", "main", "ff83d5baac004aafbe6b372ffa6f8227")
FACE_MULTICULTURALITY_MODEL = ("ethnicity-demographics-recognition", "clarifai", "main", "b2897edbda314615856039fb0c489796")
GENERAL_DETECTION_MODEL = ("general-image-detection", "clarifai", "main", "1580bb1932594c93b7e2e04456af7c6f")
CELEBRITY_DETECTION_MODEL = ("celebrity-face-detection", "clarifai", "main", "2ba4d0b0e53043f38dbbed49e03917b6")

# --- gRPC Setup ---
channel = ClarifaiChannel.get_grpc_channel()
stub = service_pb2_grpc.V2Stub(channel)
metadata = (('authorization', 'Key ' + CLARIFAI_PAT),)
requestUserDataObject = resources_pb2.UserAppIDSet(user_id=REQUEST_USER_ID, app_id=REQUEST_APP_ID)

def _call_clarifai_model(video_url: str, model_details: tuple, sample_ms: int) -> Optional[service_pb2.MultiOutputResponse]:
    """Helper function to call a specific Clarifai model for video analysis."""
    model_id, model_user_id, model_app_id = model_details[:3]
    model_version_id = model_details[3] if len(model_details) > 3 else None

    print(f"Calling Clarifai model: {model_id} (Owner: {model_user_id}/{model_app_id}) for video: {video_url}")
    try:
        request = service_pb2.PostModelOutputsRequest(
            user_app_id=requestUserDataObject,
            model_id=model_id,
            version_id=model_version_id,
            inputs=[
                resources_pb2.Input(
                        data=resources_pb2.Data(
                            video=resources_pb2.Video(url=video_url)
                        )
                )
            ],
            model=resources_pb2.Model(
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

def analyze_video_multi_model(video_url: str, sample_ms: int = 1000) -> Dict[str, Any]:
    """Analyzes video using multiple Clarifai models in parallel and aggregates results."""
    all_insights = {}
    model_responses = {}

    # Dictionary mapping descriptive name to model details tuple
    models_to_call = {
        "general_recognition": GENERAL_RECOGNITION_MODEL,
        "face_detection": FACE_DETECTION_MODEL,
        "face_sentiment": FACE_SENTIMENT_MODEL,
        "face_age": FACE_AGE_MODEL,
        "face_gender": FACE_GENDER_MODEL,
        "face_multiculturality": FACE_MULTICULTURALITY_MODEL,
        "general_detection": GENERAL_DETECTION_MODEL,
        "celebrity_detection": CELEBRITY_DETECTION_MODEL,
    }

    # Create a function that will process a single model with the video URL and sample_ms already set
    def process_single_model(model_name, model_details):
        response = _call_clarifai_model(video_url, model_details, sample_ms)
        return (model_name, response)

    # Use ThreadPoolExecutor to run API calls in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        # Create a list of futures
        futures = []
        for name, model_details_tuple in models_to_call.items():
            # Submit each model processing task to the executor
            future = executor.submit(process_single_model, name, model_details_tuple)
            futures.append(future)
        
        # Collect results as they complete
        print("Waiting for model responses in parallel...")
        for future in concurrent.futures.as_completed(futures):
            try:
                name, response = future.result()
                if response:
                    print(f"✓ Received response from model: {name}")
                    model_responses[name] = response
                else:
                    print(f"✗ No response from model: {name}")
            except Exception as e:
                print(f"Error processing model: {e}")

    print(f"Completed parallel processing. Received {len(model_responses)} valid responses out of {len(models_to_call)} models.")

    # --- Analyze Responses ---
    if "general_recognition" in model_responses:
        all_insights["concepts"] = analyze_concepts(model_responses["general_recognition"])

    # Face analysis requires results from multiple models potentially
    face_related_responses = {k: v for k, v in model_responses.items() if k.startswith("face_")}
    if face_related_responses:
         all_insights["faces"] = analyze_faces(face_related_responses)

    if "general_detection" in model_responses:
        all_insights["objects"] = analyze_objects(model_responses["general_detection"])

    if "celebrity_detection" in model_responses:
        all_insights["celebrities"] = analyze_celebrities(model_responses["celebrity_detection"])

    # --- Calculate Overall Video Stats ---
    total_frames_analyzed = 0
    if model_responses:
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
    """Download a video using yt-dlp with improved error handling for YouTube CAPTCHA issues."""
    if not output_path:
        # Generate a filename based on the URL
        output_path = f"temp_video_{os.path.basename(url).split('?')[0]}.mp4"
    
    print(f"Downloading video from: {url}")
    
    # Enhanced yt-dlp options to bypass YouTube restrictions
    ydl_opts = {
        'format': 'mp4',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': False,
        # Add these options to help bypass CAPTCHA issues
        'geo_bypass': True,
        'geo_bypass_country': 'US',
        'skip_download': False,
        'noplaylist': True,
        # Use a random user agent to help avoid bot detection
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        # Retry mechanism for temporary failures
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
        'retry_sleep_functions': {
            'http': lambda x: 5 * (2 ** (x - 1)),
            'fragment': lambda x: 5 * (2 ** (x - 1)),
            'file_access': lambda x: 5,
        }
    }
    
    # Attempt to download with increasing levels of fallback
    try:
        # First attempt - standard download
        command = ["yt-dlp", "-f", "mp4", "-o", output_path, url]
        subprocess.run(command, check=True, capture_output=True, text=True)
        if os.path.exists(output_path):
            print(f"Successfully downloaded video to {output_path}")
            return output_path
        else:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
            print(f"yt-dlp stderr: {result.stderr}")
            raise Exception("Download failed: file not found post-execution.")
    except subprocess.CalledProcessError as e:
        print(f"Initial download attempt failed: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        print("Trying alternative download methods...")
        
        try:
            # Second attempt - use YouTube embedded player URL which sometimes bypasses restrictions
            if 'youtube.com' in url or 'youtu.be' in url:
                # Extract video ID
                if 'youtube.com' in url:
                    video_id = url.split('v=')[-1].split('&')[0]
                elif 'youtu.be' in url:
                    video_id = url.split('/')[-1].split('?')[0]
                elif 'shorts' in url:
                    video_id = url.split('/')[-1].split('?')[0]
                else:
                    video_id = None
                
                if video_id:
                    # Try embedded player URL
                    embedded_url = f"https://www.youtube.com/embed/{video_id}"
                    print(f"Trying embedded URL: {embedded_url}")
                    try:
                        subprocess.run(['yt-dlp', '-f', 'mp4', '-o', output_path, embedded_url], check=True, capture_output=True, text=True)
                        if os.path.exists(output_path):
                            print(f"Successfully downloaded video using embedded URL to {output_path}")
                            return output_path
                    except subprocess.CalledProcessError as embed_error:
                        print(f"Embedded URL download failed: {embed_error.stderr if hasattr(embed_error, 'stderr') else str(embed_error)}")
            
            # Third attempt - use full ydl_opts with python interface
            try:
                print("Trying with extended options...")
                import yt_dlp
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                if os.path.exists(output_path):
                    print(f"Successfully downloaded video with extended options to {output_path}")
                    return output_path
                    
                print("Download completed but file not found")
            except Exception as ydl_error:
                print(f"Extended options download failed: {ydl_error}")
            
            # Final attempt - try to find a public non-YouTube proxy or alternative
            if 'youtube.com' in url or 'youtu.be' in url:
                try:
                    # Convert YouTube URL to a format that might work with a proxy service
                    if 'youtube.com' in url:
                        video_id = url.split('v=')[-1].split('&')[0]
                    elif 'youtu.be' in url:
                        video_id = url.split('/')[-1].split('?')[0]
                    elif 'shorts' in url:
                        video_id = url.split('/')[-1].split('?')[0]
                    else:
                        raise Exception("Could not extract YouTube video ID")
                    
                    # Try using a proxy service (Invidious instance)
                    proxy_url = f"https://vid.puffyan.us/watch?v={video_id}"
                    print(f"Trying proxy URL: {proxy_url}")
                    subprocess.run(['yt-dlp', '-f', 'mp4', '-o', output_path, proxy_url], check=True, capture_output=True, text=True)
                    
                    if os.path.exists(output_path):
                        print(f"Successfully downloaded video via proxy to {output_path}")
                        return output_path
                except Exception as proxy_error:
                    print(f"Proxy download attempt failed: {proxy_error}")
            
            # If everything fails but we're analyzing a YouTube video,
            # return an error with specific instructions about CAPTCHA restrictions
            if 'youtube.com' in url or 'youtu.be' in url:
                raise Exception(
                    "YouTube CAPTCHA restriction detected. This video requires human verification. "
                    "Consider using another video source that doesn't require CAPTCHA verification."
                )
            else:
                # For other sources
                raise Exception(f"Video download failed after multiple attempts: {e}")
                
        except Exception as inner_e:
            print(f"All download attempts failed: {inner_e}")
            raise Exception(f"Video download failed: {str(inner_e)}")
    except Exception as e:
        raise Exception(f"Video download failed: {str(e)}")
    
    # Should not reach here if all is well
    if os.path.exists(output_path):
        return output_path
    else:
        raise Exception("Download failed: file not found after all download attempts.")

# --- Main Execution ---
if __name__ == "__main__":
    video_url_source = "https://www.youtube.com/shorts/DEBPsPXFww0"
    local_filename = "temp_video_" + os.path.basename(video_url_source).split('?')[0] + ".mp4"
    s3_object_key = "videos/" + local_filename
    local_path = None
    result = {}

    try:
        # 1. Download
        local_path = download_video_with_ytdlp(video_url_source, output_path=local_filename)

        # 2. Upload to S3
        s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)

        # 3. Analyze using S3 URL
        print("--- Starting Multi-Model Analysis ---")
        clarifai_result = analyze_video_multi_model(s3_video_url, sample_ms=125)  # Analyze at 8 FPS (1000ms/8 = 125ms)
        print("--- Combined Analysis Results ---")
        print(json.dumps(clarifai_result, indent=2))

        # 4. Generate initial analysis using Gemini
        print("\n--- Generating Initial Analysis ---")
        initial_analysis = analyze_video_output(clarifai_result)
        print("--- Initial Analysis Complete ---")
        print(f"Initial analysis saved to: analysis_results/analysis_{initial_analysis['timestamp']}.json")

        # 5. Generate structured analysis
        print("\n--- Generating Structured Analysis ---")
        structured_result = process_analysis(initial_analysis)
        print("--- Structured Analysis Complete ---")
        print("Structured analysis has been saved and is ready for frontend use")

    except Exception as e:
        print("--- An error occurred during the process ---")
        print(f"{e}")

    finally:
        # 6. Clean up local file
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                print("Cleaned up local file: {local_path}")
            except OSError as e:
                print(f"Error deleting file {local_path}: {e}")

