from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import threading
import time
from narrative_analyzer import analyze_video_with_gemini
import uuid
from datetime import datetime
from dashboard_processor import DashboardProcessor
from clarif_ai_insights import (
    download_video_with_ytdlp, 
    analyze_video_multi_model, 
    upload_to_s3, 
    S3_BUCKET_NAME
)
from s3_utils import download_json_from_s3
from inference_layer import analyze_video_output
from structured_analysis import process_analysis
from unified_analysis import analyze_video as analyze_video_unified
from api_routes import analysis_bp
import traceback
import atexit
import subprocess
import concurrent.futures

app = Flask(__name__)
#comment out the CORS middleware to avoid duplicate headers
# Create an after_request handler to ensure CORS headers are properly set
@app.after_request
def after_request(response):
    # Get the origin from the request headers
    origin = request.headers.get('Origin', '')
    
    # List of allowed origins
    allowed_origins = ['https://branded-content-ai.vercel.app', 'http://localhost:3000']
    
    # Check if the request origin is in our list of allowed origins
    if origin in allowed_origins:
        response.headers.set('Access-Control-Allow-Origin', origin)
        response.headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.set('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.set('Access-Control-Allow-Credentials', 'true')
    
    return response
    
# Comment out the CORS middleware to avoid duplicate headers
# CORS(app, resources={r"/*": {
#     "origins": ["https://branded-contentai.vercel.app", "http://localhost:3000"],
#     "supports_credentials": True
# }})

processor = DashboardProcessor()

# Add a root route for the homepage
@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "status": "online",
        "message": "Branded Content AI API is running",
        "api_endpoints": [
            "/api/analyses",
            "/api/analyze-unified",
            "/api/saved-analyses",
            "/api/analysis-progress/{id}"
        ]
    })

# Register the analysis blueprint
app.register_blueprint(analysis_bp)

# In-memory storage for analyses and tracking analysis progress
analyses = []
analysis_progress = {}  # Structure: {analysis_id: {progress, step, status, result}}

@app.route('/api/analyses', methods=['GET'])
def get_analyses():
    # This might return stale in-memory data, but keep for compatibility if needed
    return jsonify({"analyses": analyses})

@app.route('/api/analyze-url', methods=['POST'])
def analyze_url():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    try:
        # Get analysis from Gemini
        analysis = analyze_video_with_gemini(url, is_url_prompt=True)
        
        # Process the analysis through the dashboard processor
        processed_data = processor.process_analysis({
            "analysis": analysis["analysis"],
            "video_name": "URL Analysis",
            "timestamp": time.strftime("%Y%m%d_%H%M%S")
        })
        
        return jsonify(processed_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
            
        file = request.files['file']
        if not file:
            return jsonify({"error": "No file selected"}), 400
            
        # Save the uploaded file temporarily
        temp_path = "temp_video.mp4"
        file.save(temp_path)
        print(f"\nReceived file for analysis: {file.filename}")
        
        try:
            # Analyze the video file
            result = analyze_video_with_gemini(temp_path)
            
            if "error" in result:
                return jsonify({"error": result["error"]}), 500
                
            # Create analysis ID and timestamp
            analysis_id = str(uuid.uuid4())
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            
            # Process the analysis through the dashboard processor
            processed_data = processor.process_analysis({
                "analysis": result["analysis"],
                "video_name": file.filename,
                "timestamp": timestamp,
                "id": analysis_id
            })
                
            # Store the analysis (in memory - limited use)
            analyses.append({
                "metadata": {
                    "id": analysis_id,
                    "video_name": file.filename,
                    "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
                },
                "dashboard_data": processed_data
            })
                
            return jsonify({
                "analysis_id": analysis_id,
                "dashboard_data": processed_data
            })
            
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        print(f"Error in analyze_file: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis/<analysis_id>', methods=['GET'])
def get_analysis(analysis_id):
    """
    Get analysis data by ID from S3.
    Returns the analysis dashboard data in a format the frontend expects.
    """
    print(f"Attempting to retrieve analysis {analysis_id} from S3")
    s3_object_key = f"analysis-results/{analysis_id}.json"

    try:
        analysis_data = download_json_from_s3(S3_BUCKET_NAME, s3_object_key)

        if analysis_data:
            print(f"Successfully retrieved analysis {analysis_id} from S3")
            # The data from S3 should already be in the correct format
            return jsonify(analysis_data), 200
        else:
            # If not found in S3, check for an error file as a fallback
            print(f"Analysis {analysis_id} not found in S3. Checking for error file.")
            s3_error_key = f"analysis-results/{analysis_id}_error.json"
            error_data = download_json_from_s3(S3_BUCKET_NAME, s3_error_key)
            if error_data:
                 print(f"Found error file for analysis {analysis_id} in S3")
                 # Return the error data, maybe with a different status code if desired?
                 # For now, return 200 but let frontend handle the error flag within data
                 return jsonify(error_data), 200
            else:
                 # If neither main nor error file found
                 print(f"Analysis {analysis_id} not found in S3 (neither main nor error file)")
                 return jsonify({
                     "error": "Analysis not found",
                     "metadata": {"id": analysis_id},
                     "summary": {
                         "content_overview": "Analysis data not found",
                         "overall_performance_score": 0
                     }
                 }), 404

    except Exception as e:
        # Handle potential errors during S3 download (e.g., credentials, permissions)
        print(f"Error retrieving analysis {analysis_id} from S3: {e}")
        traceback.print_exc()
        return jsonify({
            "error": f"Failed to retrieve analysis from storage: {str(e)}",
            "metadata": {"id": analysis_id}
        }), 500

@app.route('/api/analysis/<analysis_id>', methods=['DELETE'])
def delete_analysis(analysis_id):
    global analyses
    initial_count = len(analyses)
    analyses = [a for a in analyses if a["metadata"]["id"] != analysis_id]
    # TODO: Add deletion from S3 as well
    print(f"Note: S3 deletion for {analysis_id} not yet implemented.")
    if len(analyses) < initial_count:
        return jsonify({"success": True})
    return jsonify({"error": "Analysis not found"}), 404

@app.route('/api/analyze-clarifai', methods=['POST'])
def analyze_clarifai():
    try:
        # Handle both URL and file uploads
        if 'url' in request.json:
            # URL-based analysis
            video_url = request.json.get('url')
            if not video_url:
                return jsonify({"error": "URL is required"}), 400
                
            video_name = "URL Analysis - " + video_url.split('/')[-1]
            local_filename = "temp_video_" + os.path.basename(video_url).split('?')[0] + ".mp4"
            s3_object_key = "videos/" + local_filename
            local_path = None
            
            try:
                # 1. Download
                local_path = download_video_with_ytdlp(video_url, output_path=local_filename)
                
                # 2. Upload to S3
                s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
                
                # Process video with Clarifai
                return process_clarifai_video(s3_video_url, video_name)
                
            finally:
                # Clean up local file
                if local_path and os.path.exists(local_path):
                    try:
                        os.remove(local_path)
                    except OSError as e:
                        print(f"Error deleting file {local_path}: {e}")
                        
        elif 'file' in request.files:
            # File-based analysis
            file = request.files['file']
            if not file:
                return jsonify({"error": "No file selected"}), 400
                
            # Save the uploaded file temporarily
            temp_path = "temp_video.mp4"
            file.save(temp_path)
            print(f"\nReceived file for analysis: {file.filename}")
            
            # Upload to S3
            s3_object_key = "videos/" + file.filename
            s3_video_url = upload_to_s3(temp_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
            
            try:
                # Process video with Clarifai
                return process_clarifai_video(s3_video_url, file.filename)
            finally:
                # Clean up the temporary file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        else:
            return jsonify({"error": "Either URL or file must be provided"}), 400
            
    except Exception as e:
        print(f"Error in analyze_clarifai: {e}")
        return jsonify({"error": str(e)}), 500

def process_clarifai_video(video_url, video_name):
    """Process a video with Clarifai and generate structured analysis."""
    try:
        # Create analysis ID and timestamp
        analysis_id = str(uuid.uuid4())
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        # 1. Analyze using Clarifai models
        print("--- Starting Multi-Model Analysis ---")
        clarifai_result = analyze_video_multi_model(video_url, sample_ms=125)  # Analyze at 8 FPS
        
        # 2. Generate initial analysis using Gemini
        print("\n--- Generating Initial Analysis ---")
        initial_analysis = analyze_video_output(clarifai_result)
        print("--- Initial Analysis Complete ---")
        
        # 3. Generate structured analysis
        print("\n--- Generating Structured Analysis ---")
        structured_result = process_analysis(initial_analysis)
        print("--- Structured Analysis Complete ---")
        
        # 4. Store analysis results (in memory - limited use)
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "video_name": video_name,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
            },
            "raw_analysis": initial_analysis,
            "structured_analysis": structured_result
        })
        
        return jsonify({
            "analysis_id": analysis_id,
            "raw_analysis": initial_analysis,
            "structured_analysis": structured_result
        })
        
    except Exception as e:
        print(f"Error in process_clarifai_video: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze-unified', methods=['POST'])
def analyze_unified():
    """Endpoint for unified analysis combining both Gemini and ClarifAI insights."""
    try:
        analysis_id = str(uuid.uuid4())
        analysis_name = None # Initialize analysis_name

        # Initialize the analysis progress tracking
        analysis_progress[analysis_id] = {
            "progress": 0,
            "step": 0,
            "status": "initializing",
            "result": None,
            "name": "Processing..." # Default name while processing
        }
        
        # Define a progress callback function
        def update_progress_callback(status, progress):
            # Map stages to appropriate step numbers and statuses
            status_mapping = {
                "initializing": {"step": 0, "status": "initializing"},
                "downloading_video": {"step": 1, "status": "downloading_video"},
                "download_complete": {"step": 2, "status": "download_complete"},
                "uploading_to_s3": {"step": 3, "status": "uploading_to_s3"},
                "running_gemini_analysis": {"step": 3, "status": "running_gemini_analysis"},
                "running_clarifai_analysis": {"step": 4, "status": "running_clarifai_analysis"},
                "processing_with_ai_models": {"step": 6, "status": "processing_with_ai_models"},
                "gemini_started": {"step": 3, "status": "running_gemini_analysis"},
                "clarifai_started": {"step": 4, "status": "running_clarifai_analysis"},
                "gemini_complete": {"step": 6, "status": "gemini_analysis_complete"},
                "clarifai_complete": {"step": 8, "status": "clarifai_analysis_complete"},
                "generating_unified": {"step": 9, "status": "generating_unified_analysis"},
                "validating_unified": {"step": 10, "status": "validating_analysis"},
                "finalizing": {"step": 11, "status": "finalizing_results"},
                "completed": {"step": 12, "status": "completed"},
                "error": {"step": 0, "status": "error"}
            }
            
            # Update the progress tracking
            if status in status_mapping:
                mapped = status_mapping[status]
                analysis_progress[analysis_id]["step"] = mapped["step"]
                analysis_progress[analysis_id]["status"] = mapped["status"]
            
            # Always update the progress percentage
            analysis_progress[analysis_id]["progress"] = progress
        
        # Check if we're getting a URL or a file upload
        content_type = request.headers.get('Content-Type', '')
        
        # Handle URL-based analysis (application/json)
        if 'application/json' in content_type and request.json:
            video_url = request.json.get('url')
            analysis_name = request.json.get('name', 'URL Analysis') # Get name from JSON
            if not video_url:
                return jsonify({"error": "URL is required"}), 400
            
            # Set analysis name in progress tracker
            analysis_progress[analysis_id]["name"] = analysis_name

            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_url,
                args=(analysis_id, video_url, analysis_name, update_progress_callback)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "analysis_id": analysis_id,
                "status": "processing",
                "message": "Analysis started successfully. Check progress with the progress endpoint."
            })
            
        # Handle file upload analysis (multipart/form-data)
        elif 'multipart/form-data' in content_type or request.files:
            print(f"Processing file upload with content type: {content_type}")
            print(f"Files in request: {list(request.files.keys())}")
            
            if 'file' not in request.files:
                return jsonify({"error": "No file part in the request"}), 400
                
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({"error": "No file selected"}), 400
            
            # Get analysis name from form data (use filename as fallback)
            analysis_name = request.form.get('name', file.filename)
            if not analysis_name.strip(): # Handle empty name field
                 analysis_name = file.filename

            print(f"Received file upload: {file.filename}, Analysis Name: {analysis_name}")
            
            # Set analysis name in progress tracker
            analysis_progress[analysis_id]["name"] = analysis_name

            # Save the uploaded file temporarily
            temp_path = f"temp_video_{analysis_id}.mp4"
            file.save(temp_path)
            print(f"Saved temporary file to {temp_path}")
            
            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_file,
                args=(analysis_id, temp_path, file.filename, analysis_name, update_progress_callback)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "analysis_id": analysis_id,
                "status": "processing",
                "message": "Analysis started successfully. Check progress with the progress endpoint."
            })
            
        else:
            return jsonify({"error": "Either URL or file must be provided. Ensure Content-Type is set correctly (application/json for URLs or multipart/form-data for files)."}), 400
            
    except Exception as e:
        print(f"Error in analyze_unified: {e}")
        traceback.print_exc()  # Print full traceback for debugging
        return jsonify({"error": str(e)}), 500

@app.route('/api/analysis-progress/<analysis_id>', methods=['GET'])
def get_analysis_progress(analysis_id):
    """Get the current progress of an ongoing analysis."""
    if analysis_id not in analysis_progress:
        # Before returning 404, check if the result exists in S3
        print(f"Progress for {analysis_id} not in memory. Checking S3...")
        s3_object_key = f"analysis-results/{analysis_id}.json"
        try:
            analysis_data = download_json_from_s3(S3_BUCKET_NAME, s3_object_key)
            if analysis_data:
                print(f"Found completed analysis {analysis_id} in S3 during progress check.")
                # Update in-memory cache if needed (optional)
                analysis_progress[analysis_id] = {
                    "progress": 100,
                    "step": 12, # Assuming 12 is the completed step
                    "status": "completed",
                    "result": analysis_data
                }
                return jsonify(analysis_progress[analysis_id])
            else:
                # Check for error file
                s3_error_key = f"analysis-results/{analysis_id}_error.json"
                error_data = download_json_from_s3(S3_BUCKET_NAME, s3_error_key)
                if error_data:
                    print(f"Found error analysis {analysis_id} in S3 during progress check.")
                    analysis_progress[analysis_id] = {
                        "progress": 0,
                        "step": 0,
                        "status": "error",
                        "result": error_data
                    }
                    return jsonify(analysis_progress[analysis_id])
                else:
                    print(f"Analysis {analysis_id} not found in memory or S3.")
                    return jsonify({"error": "Analysis ID not found or expired"}), 404
        except Exception as e:
            print(f"Error checking S3 for analysis {analysis_id} during progress check: {e}")
            # Fallback to 404 if S3 check fails
            return jsonify({"error": "Analysis ID not found or error checking status"}), 404

    progress_data = analysis_progress[analysis_id]

    # If analysis is complete in memory, include the result (already handled by S3 check?)
    # Keep this for safety / if S3 check fails but memory has completion
    if progress_data["status"] == "completed" and progress_data.get("result"):
        return jsonify({
            "analysis_id": analysis_id,
            "progress": progress_data["progress"],
            "step": progress_data["step"],
            "status": progress_data["status"],
            "result": progress_data["result"]
        })
    elif progress_data["status"] == "error" and progress_data.get("result"):
         return jsonify({
            "analysis_id": analysis_id,
            "progress": progress_data["progress"],
            "step": progress_data["step"],
            "status": progress_data["status"],
            "result": progress_data["result"] # Include error details
        })

    # Default: Return current in-memory progress
    return jsonify({
        "analysis_id": analysis_id,
        "progress": progress_data["progress"],
        "step": progress_data["step"],
        "status": progress_data["status"]
    })

def process_unified_analysis_url(analysis_id, video_url, analysis_name, update_progress_callback):
    """Process a URL-based analysis in the background and update progress."""
    local_path = None # Define local_path here for cleanup scope
    try:
        update_progress_callback("initializing", 0)
        update_progress_callback("downloading_video", 5)
        print(f"Starting unified analysis for video URL: {video_url} (Name: {analysis_name}, ID: {analysis_id})")

        def progress_callback(stage, progress_pct):
            update_progress_callback(stage, progress_pct)

        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            print("YouTube URL detected - attempting analysis...")

        unified_result = analyze_video_unified(video_url, analysis_id, analysis_name, progress_callback)

        update_progress_callback("finalizing", 90)

        # Construct final data (includes saving to S3 via analyze_video_unified -> save_unified_analysis)
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "analysis_name": analysis_name,
                "video_url": video_url,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"],
                "confidence_index": unified_result.get("metadata", {}).get("confidence_index", 75)
            },
             **(unified_result if isinstance(unified_result, dict) else {})
        }
        # Ensure ID exists (should be redundant now but safe)
        if "id" not in result_with_metadata.get("metadata", {}):
             result_with_metadata["metadata"]["id"] = analysis_id
        if "analysis_id" not in result_with_metadata:
             result_with_metadata["analysis_id"] = analysis_id
        if "content_name" not in result_with_metadata:
             result_with_metadata["content_name"] = video_url.split('/')[-1] if '/' in video_url else video_url

        # Update progress to completed with the result
        if analysis_id in analysis_progress:
            analysis_progress[analysis_id]["result"] = result_with_metadata # Store result in memory
        update_progress_callback("completed", 100)

        print(f"Unified analysis completed for: {video_url} (Name: {analysis_name})")

    except Exception as e:
        print(f"Error processing URL analysis (Name: {analysis_name}): {e}")
        update_progress_callback("error", 0)
        if analysis_id in analysis_progress:
            error_result = {
                 "metadata": { "id": analysis_id, "analysis_name": analysis_name, "video_url": video_url },
                 "error": str(e),
                 "message": "Analysis failed. Please check the server logs for details.",
                 "timestamp": datetime.now().isoformat()
            }
            analysis_progress[analysis_id]["result"] = error_result
            analysis_progress[analysis_id]["status"] = "error"
            # Attempt to save error report to S3
            try:
                from unified_analysis import save_unified_analysis # Import locally if needed
                save_unified_analysis(error_result)
            except Exception as save_e:
                print(f"Could not save error analysis report: {save_e}")

    finally:
         # Clean up temp downloaded file if it exists (check unified_analysis.py for actual path)
         # This assumes download happens within analyze_video_unified now
         pass # Add cleanup logic here if needed based on where download occurs

def process_unified_analysis_file(analysis_id, file_path, filename, analysis_name, update_progress_callback):
    """Process a file-based analysis in the background and update progress."""
    try:
        update_progress_callback("initializing", 5)
        print(f"Starting file analysis process for {filename} (Name: {analysis_name}, ID: {analysis_id})")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Temporary file {file_path} not found")

        update_progress_callback("preparing", 15)
        print(f"Starting unified analysis for video file: {filename}")

        def progress_callback(stage, progress_pct):
            update_progress_callback(stage, progress_pct)
            print(f"Analysis progress: {stage} - {progress_pct}%")

        # Pass analysis_id and analysis_name to the unified function
        unified_result = analyze_video_unified(file_path, analysis_id, analysis_name, progress_callback)

        # Get S3 URL from the result if available (primarily for metadata display)
        s3_video_url = unified_result.get("metadata", {}).get("s3_video_url", f"file://{filename}")

        update_progress_callback("finalizing", 95) # Update progress after analysis

        # Construct final data structure
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "analysis_name": analysis_name,
                "video_url": s3_video_url, # Store S3 URL or file indicator
                "filename": filename,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"],
                "confidence_index": unified_result.get("metadata", {}).get("confidence_index", 75)
            },
            **(unified_result if isinstance(unified_result, dict) else {})
        }
        # Ensure ID exists (should be redundant now but safe)
        if "id" not in result_with_metadata.get("metadata", {}):
             result_with_metadata["metadata"]["id"] = analysis_id
        if "analysis_id" not in result_with_metadata:
             result_with_metadata["analysis_id"] = analysis_id
        if "content_name" not in result_with_metadata:
             result_with_metadata["content_name"] = filename

        # Update progress to completed with the result
        if analysis_id in analysis_progress:
            analysis_progress[analysis_id]["result"] = result_with_metadata # Store result in memory
        update_progress_callback("completed", 100)

        print(f"Unified analysis completed for: {filename} (Name: {analysis_name})")

    except Exception as e:
        print(f"Error processing file analysis (Name: {analysis_name}): {e}")
        update_progress_callback("error", 0)
        if analysis_id in analysis_progress:
             error_result = {
                 "metadata": { "id": analysis_id, "analysis_name": analysis_name, "filename": filename },
                 "error": str(e),
                 "message": "Analysis failed. Please check the server logs for details.",
                 "timestamp": datetime.now().isoformat()
            }
             analysis_progress[analysis_id]["result"] = error_result
             analysis_progress[analysis_id]["status"] = "error"
             # Attempt to save error report to S3
             try:
                 from unified_analysis import save_unified_analysis # Import locally if needed
                 save_unified_analysis(error_result)
             except Exception as save_e:
                 print(f"Could not save error analysis report: {save_e}")

    finally:
        # Clean up temp file
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleaned up temp file: {file_path}")
            except Exception as e_rem:
                 print(f"Error removing temp file {file_path}: {e_rem}")

# Remove compatibility route or update it
@app.route('/api/analyses', methods=['GET'])
def get_analyses_compat():
     print("Warning: /api/analyses GET endpoint is deprecated. Use /api/saved-analyses.")
     # Return empty list or redirect?
     return jsonify({"analyses": []})

# Close MongoDB connection when the app is terminated
def shutdown_mongodb():
    print("Application shutting down, closing MongoDB connection...")
    MongoDBStorage.close_connection()

# Register the shutdown function to run at exit
atexit.register(shutdown_mongodb)

def download_video_with_ytdlp(video_url, output_path=None):
    """Download a video using yt-dlp with improved error handling for YouTube CAPTCHA issues."""
    if not output_path:
        # Generate a filename based on the URL
        output_path = f"temp_video_{os.path.basename(video_url).split('?')[0]}.mp4"
    
    print(f"Downloading video from: {video_url}")
    
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
        subprocess.run(['yt-dlp', '-f', 'mp4', '-o', output_path, video_url], check=True)
        print(f"Successfully downloaded video to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Initial download attempt failed: {e}")
        print("Trying alternative download methods...")
        
        try:
            # Second attempt - use YouTube embedded player URL which sometimes bypasses restrictions
            if 'youtube.com' in video_url or 'youtu.be' in video_url:
                # Extract video ID
                if 'youtube.com' in video_url:
                    video_id = video_url.split('v=')[-1].split('&')[0]
                elif 'youtu.be' in video_url:
                    video_id = video_url.split('/')[-1].split('?')[0]
                elif 'shorts' in video_url:
                    video_id = video_url.split('/')[-1].split('?')[0]
                else:
                    video_id = None
                
                if video_id:
                    # Try embedded player URL
                    embedded_url = f"https://www.youtube.com/embed/{video_id}"
                    print(f"Trying embedded URL: {embedded_url}")
                    subprocess.run(['yt-dlp', '-f', 'mp4', '-o', output_path, embedded_url], check=True)
                    print(f"Successfully downloaded video using embedded URL to {output_path}")
                    return output_path
            
            # Third attempt - use full ydl_opts with python interface
            print("Trying with extended options...")
            import yt_dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            if os.path.exists(output_path):
                print(f"Successfully downloaded video with extended options to {output_path}")
                return output_path
                
            raise Exception("Download completed but file not found")
            
        except Exception as inner_e:
            print(f"All download attempts failed: {inner_e}")
            
            # Final attempt - try to find a public non-YouTube proxy or alternative
            if 'youtube.com' in video_url or 'youtu.be' in video_url:
                try:
                    # Convert YouTube URL to a format that might work with a proxy service
                    if 'youtube.com' in video_url:
                        video_id = video_url.split('v=')[-1].split('&')[0]
                    elif 'youtu.be' in video_url:
                        video_id = video_url.split('/')[-1].split('?')[0]
                    elif 'shorts' in video_url:
                        video_id = video_url.split('/')[-1].split('?')[0]
                    else:
                        raise Exception("Could not extract YouTube video ID")
                    
                    # Try using a proxy service
                    proxy_url = f"https://vid.puffyan.us/watch?v={video_id}"
                    print(f"Trying proxy URL: {proxy_url}")
                    subprocess.run(['yt-dlp', '-f', 'mp4', '-o', output_path, proxy_url], check=True)
                    
                    if os.path.exists(output_path):
                        print(f"Successfully downloaded video via proxy to {output_path}")
                        return output_path
                except Exception as proxy_error:
                    print(f"Proxy download attempt failed: {proxy_error}")
            
            # If all download attempts fail, raise the original error
            raise Exception(f"Video download failed after multiple attempts: {inner_e}")
            
    # Return the path to the downloaded file
    return output_path

if __name__ == '__main__':
    # For local development, use:
    # app.run(debug=True, port=5000)
    
    # For production deployment, use:
    app.run(host='0.0.0.0', port=5000, debug=False) 
