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
from inference_layer import analyze_video_output
from structured_analysis import process_analysis
from unified_analysis import analyze_video as analyze_video_unified
from mongodb_storage import MongoDBStorage
from api_routes import analysis_bp
import traceback
import atexit
import pymongo
import subprocess

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

# Initialize MongoDB connection at application startup
print("Initializing MongoDB connection...")
try:
    # Set longer connection timeouts for production environment
    mongodb_collection = MongoDBStorage.get_collection(
        server_selection_timeout_ms=5000,  # 5 seconds
        connect_timeout_ms=5000,
        socket_timeout_ms=5000
    )
    print(f"MongoDB initialized successfully")
except Exception as e:
    print(f"Warning: Could not initialize MongoDB connection: {e}")
    traceback.print_exc()

# In-memory storage for analyses and tracking analysis progress
analyses = []
analysis_progress = {}  # Structure: {analysis_id: {progress, step, status, result}}

@app.route('/api/analyses', methods=['GET'])
def get_analyses():
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
                
            # Store the analysis
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
    for analysis in analyses:
        if analysis["metadata"]["id"] == analysis_id:
            return jsonify(analysis["dashboard_data"])
    return jsonify({"error": "Analysis not found"}), 404

@app.route('/api/analysis/<analysis_id>', methods=['DELETE'])
def delete_analysis(analysis_id):
    global analyses
    initial_count = len(analyses)
    analyses = [a for a in analyses if a["metadata"]["id"] != analysis_id]
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
        
        # 4. Store analysis results
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
        
        # Initialize the analysis progress tracking
        analysis_progress[analysis_id] = {
            "progress": 0,
            "step": 0,
            "status": "initializing",
            "result": None
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
        if 'application/json' in content_type and request.json and 'url' in request.json:
            video_url = request.json.get('url')
            if not video_url:
                return jsonify({"error": "URL is required"}), 400
            
            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_url,
                args=(analysis_id, video_url, update_progress_callback)
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
            
            print(f"Received file upload: {file.filename}, Content-Type: {file.content_type}, Size: {file.content_length}")
                
            # Save the uploaded file temporarily
            temp_path = f"temp_video_{analysis_id}.mp4"
            file.save(temp_path)
            print(f"Saved temporary file to {temp_path}")
            
            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_file,
                args=(analysis_id, temp_path, file.filename, update_progress_callback)
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
        return jsonify({"error": "Analysis ID not found"}), 404
        
    progress_data = analysis_progress[analysis_id]
    
    # If analysis is complete, include the result
    if progress_data["status"] == "completed" and progress_data["result"]:
        return jsonify({
            "analysis_id": analysis_id,
            "progress": progress_data["progress"],
            "step": progress_data["step"],
            "status": progress_data["status"],
            "result": progress_data["result"]
        })
    
    return jsonify({
        "analysis_id": analysis_id,
        "progress": progress_data["progress"],
        "step": progress_data["step"],
        "status": progress_data["status"]
    })

def process_unified_analysis_url(analysis_id, video_url, update_progress_callback):
    """Process a URL-based analysis in the background and update progress."""
    try:
        update_progress_callback("initializing", 0)
        
        # Use the unified analysis function that runs Gemini and ClarifAI in parallel
        update_progress_callback("downloading_video", 5)
        print(f"Starting unified analysis for video URL: {video_url}")
        
        # Track the progress of the analysis
        def progress_callback(stage, progress_pct):
            update_progress_callback(stage, progress_pct)
        
        # Add user-friendly YouTube check before proceeding
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            print("YouTube URL detected - attempting analysis with potential CAPTCHA handling...")
        
        # Run the unified analysis with progress callback
        try:
            unified_result = analyze_video_unified(video_url, progress_callback)
        except Exception as analysis_error:
            print(f"Error in analyze_video_unified: {analysis_error}")
            
            # Check for YouTube CAPTCHA errors specifically
            if "CAPTCHA" in str(analysis_error) or "verification" in str(analysis_error):
                # Update our progress indicator
                update_progress_callback("captcha_error", 50)
                
                # Create a user-friendly error message
                captcha_error = {
                    "error": "YouTube CAPTCHA Error",
                    "message": (
                        "The video could not be analyzed because YouTube is requiring CAPTCHA verification. "
                        "Please try another video source or upload a video file directly instead of using a YouTube URL."
                    ),
                    "metadata": {
                        "url": video_url,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                
                # Update progress to error with the error message
                if analysis_id in analysis_progress:
                    analysis_progress[analysis_id]["status"] = "error"
                    analysis_progress[analysis_id]["result"] = captcha_error
                
                update_progress_callback("error", 0)
                
                raise Exception(
                    "YouTube CAPTCHA restriction detected. This video requires human verification. "
                    "Try another video source or upload a video file directly."
                )
            
            # Re-raise the original error if not CAPTCHA related
            raise
        
        # Update progress
        update_progress_callback("finalizing", 90)
        
        # Add metadata
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "video_url": video_url,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"],
                "confidence_index": unified_result.get("metadata", {}).get("confidence_index", 75)
            },
            **unified_result
        }
        
        # Save the analysis to MongoDB
        content_name = video_url.split('/')[-1] if '/' in video_url else video_url
        mongo_storage = MongoDBStorage()
        
        # Make sure result_with_metadata has all required fields
        result_with_metadata["analysis_id"] = analysis_id
        result_with_metadata["content_name"] = content_name
        
        mongo_storage.save_analysis(result_with_metadata)
        
        # Add to analyses list
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "video_url": video_url,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
            },
            "analysis_data": result_with_metadata
        })
        
        # Update progress to completed with the result
        if analysis_id in analysis_progress:
            analysis_progress[analysis_id]["result"] = result_with_metadata
        update_progress_callback("completed", 100)
        
        print(f"Unified analysis completed for: {video_url}")
        
    except Exception as e:
        print(f"Error processing URL analysis: {e}")
        
        # Set error status in progress tracker
        update_progress_callback("error", 0)
        
        # Add a helpful error message to the analysis progress
        if analysis_id in analysis_progress:
            error_result = {
                "error": str(e),
                "message": "Analysis failed. Please check the server logs for details.",
                "timestamp": datetime.now().isoformat(),
                "url": video_url
            }
            
            analysis_progress[analysis_id]["result"] = error_result
        
        # Clean up temp file on error
        local_path = f"temp_video_{analysis_id}.mp4"
        if os.path.exists(local_path):
            os.remove(local_path)

def process_unified_analysis_file(analysis_id, file_path, filename, update_progress_callback):
    """Process a file-based analysis in the background and update progress."""
    try:
        update_progress_callback("initializing", 5)
        print(f"Starting file analysis process for {filename} at {file_path}")
        
        # Check if file exists and is accessible
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Temporary file {file_path} not found")
        
        # Check file size
        file_size = os.path.getsize(file_path)
        print(f"File size: {file_size} bytes")
        
        # Use the unified analysis function with the local file path directly
        # This allows Gemini to use direct file upload instead of URL-based analysis
        update_progress_callback("preparing", 15)
        print(f"Starting unified analysis for video file: {filename}")
        
        # Track the progress of the analysis
        def progress_callback(stage, progress_pct):
            update_progress_callback(stage, progress_pct)
            print(f"Analysis progress: {stage} - {progress_pct}%")
        
        # Run the unified analysis with progress callback using the local file path
        # S3 upload will happen inside the analysis pipeline only for ClarifAI
        unified_result = analyze_video_unified(file_path, progress_callback)
        
        # Get S3 URL from the result if available, or upload to S3 if needed
        s3_video_url = None
        if "metadata" in unified_result and "s3_video_url" in unified_result["metadata"]:
            s3_video_url = unified_result["metadata"]["s3_video_url"]
        else:
            # Upload to S3 for storage if not already done in the analysis
            update_progress_callback("uploading_to_s3", 85)
            s3_object_key = f"videos/{os.path.basename(file_path)}"
            try:
                s3_video_url = upload_to_s3(file_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
                print(f"Successfully uploaded to S3: {s3_video_url}")
            except Exception as e:
                print(f"Error uploading to S3 for storage: {e}")
                # Continue even if S3 upload fails
                s3_video_url = f"file://{filename}"
        
        # Update progress
        update_progress_callback("finalizing", 90)
        
        # Add metadata
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "video_url": s3_video_url,
                "filename": filename,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"],
                "confidence_index": unified_result.get("metadata", {}).get("confidence_index", 75)
            },
            **unified_result
        }
        
        # Save the analysis to MongoDB
        content_name = filename
        mongo_storage = MongoDBStorage()
        
        # Make sure result_with_metadata has all required fields
        result_with_metadata["analysis_id"] = analysis_id
        result_with_metadata["content_name"] = content_name
        
        mongo_storage.save_analysis(result_with_metadata)
        
        # Add to analyses list
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "video_url": s3_video_url,
                "filename": filename,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
            },
            "analysis_data": result_with_metadata
        })
        
        # Update progress to completed with the result
        if analysis_id in analysis_progress:
            analysis_progress[analysis_id]["result"] = result_with_metadata
        update_progress_callback("completed", 100)
        
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)
            
        print(f"Unified analysis completed for: {filename}")
        
    except Exception as e:
        print(f"Error processing file analysis: {e}")
        update_progress_callback("error", 0)
        
        # Clean up temp file on error
        if os.path.exists(file_path):
            os.remove(file_path)

@app.route('/api/saved-analyses', methods=['GET'])
def get_saved_analyses():
    """Get saved analyses from MongoDB storage"""
    try:
        limit = int(request.args.get('limit', 20))
        skip = int(request.args.get('skip', 0))
        
        # Get analyses from MongoDB with a quick timeout
        try:
            # Return empty immediately if collection is empty
            total_count = 0
            stored_analyses = []
            
            # Use a quick timeout for MongoDB operations - this will either
            # connect quickly or fail quickly, preventing the frontend from waiting
            client = pymongo.MongoClient(
                os.getenv("MONGODB_URI"),
                serverSelectionTimeoutMS=1000,  # 1 second timeout
                connectTimeoutMS=1000,
                socketTimeoutMS=1000
            )
            
            print("Connecting to MongoDB...")
            
            # Check if the database exists first
            db_names = client.list_database_names()
            db_name = os.getenv("MONGODB_DB", "branded_content_ai")
            
            if db_name not in db_names:
                print(f"Database '{db_name}' does not exist. Returning empty list.")
                return jsonify({"analyses": [], "total": 0})
                
            # Database exists, access it
            db = client[db_name]
            
            # Check if the collection exists
            coll_name = os.getenv("MONGODB_ANALYSES_COLLECTION", "analyses")
            if coll_name not in db.list_collection_names():
                print(f"Collection '{coll_name}' does not exist. Returning empty list.")
                return jsonify({"analyses": [], "total": 0})
                
            # Collection exists, access it
            coll = db[coll_name]
            
            # Try a quick operation to test connection and count documents
            total_count = coll.count_documents({})
            print(f"Total analyses in collection: {total_count}")
            
            # If we have documents, fetch them with pagination
            if total_count > 0:
                cursor = coll.find({}).sort("timestamp", -1).skip(skip).limit(limit)
                for doc in cursor:
                    if "_id" in doc:
                        doc["_id"] = str(doc["_id"])
                    stored_analyses.append(doc)
            
            client.close()
            
        except Exception as e:
            print(f"Error accessing MongoDB: {e}")
            traceback.print_exc()
            # Don't wait - just return empty list immediately
            return jsonify({"analyses": [], "total": 0})
        
        # Format analyses
        formatted_analyses = []
        for analysis in stored_analyses:
            try:
                analysis_id = analysis.get("id")
                if not analysis_id:
                    continue
                    
                # Extract video URL from metadata or fall back to content_name
                video_url = None
                if analysis.get("analysis_data", {}).get("metadata", {}).get("video_url"):
                    video_url = analysis["analysis_data"]["metadata"]["video_url"]
                elif analysis.get("content_name"):
                    video_url = analysis.get("content_name")

                formatted_analyses.append({
                    "id": analysis_id,
                    "video_url": video_url,
                    "analyzed_date": analysis.get("formatted_date", analysis.get("timestamp")),
                    "thumbnail": analysis.get("thumbnail"),
                    "content_name": analysis.get("content_name", "Unknown"),
                    "analysis_data": analysis.get("analysis_data", {})
                })
            except Exception as inner_e:
                print(f"Error processing analysis: {inner_e}")
                continue
        
        return jsonify({"analyses": formatted_analyses, "total": total_count})
    except Exception as e:
        print(f"Error in get_saved_analyses: {e}")
        traceback.print_exc()
        return jsonify({"analyses": [], "total": 0})

# Add a compatibility route that maps to our new saved-analyses API
@app.route('/api/analyses', methods=['GET'])
def get_analyses_compat():
    """Compatibility route that redirects to get_saved_analyses"""
    try:
        limit = int(request.args.get('limit', 20))
        skip = int(request.args.get('skip', 0))
        
        # Get analyses from MongoDB with a quick timeout
        try:
            # Return empty immediately if collection is empty
            stored_analyses = []
            
            # Use a quick timeout for MongoDB operations
            client = pymongo.MongoClient(
                os.getenv("MONGODB_URI"),
                serverSelectionTimeoutMS=2000,  # 2 second timeout
                connectTimeoutMS=2000,
                socketTimeoutMS=2000
            )
            db = client[os.getenv("MONGODB_DB", "branded_content_ai")]
            coll = db[os.getenv("MONGODB_ANALYSES_COLLECTION", "analyses")]
            
            # Try to fetch documents with pagination
            cursor = coll.find({}).sort("timestamp", -1).skip(skip).limit(limit)
            for doc in cursor:
                if "_id" in doc:
                    doc["_id"] = str(doc["_id"])
                stored_analyses.append(doc)
            
            client.close()
            
        except Exception as e:
            print(f"Error accessing MongoDB: {e}")
            # Don't wait - just return empty list immediately
            return jsonify({"analyses": []})
        
        # Format to match the expected format from the old API
        formatted_analyses = []
        for analysis in stored_analyses:
            try:
                analysis_id = analysis.get("id")
                if not analysis_id:
                    continue
                    
                # Extract video URL from metadata or fall back to content_name
                video_url = None
                if analysis.get("analysis_data", {}).get("metadata", {}).get("video_url"):
                    video_url = analysis["analysis_data"]["metadata"]["video_url"]
                elif analysis.get("content_name"):
                    video_url = analysis.get("content_name")

                formatted_analyses.append({
                    "metadata": {
                        "id": analysis_id,
                        "video_url": video_url,
                        "analyzed_date": analysis.get("formatted_date", analysis.get("timestamp"))
                    },
                    "analysis_data": analysis.get("analysis_data", {})
                })
            except Exception as inner_e:
                print(f"Error processing analysis {analysis.get('id')}: {inner_e}")
                continue
        
        return jsonify({"analyses": formatted_analyses})
    except Exception as e:
        print(f"Error in get_analyses_compat: {e}")
        traceback.print_exc()
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
