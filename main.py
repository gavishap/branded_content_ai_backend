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

app = Flask(__name__)
CORS(app)
processor = DashboardProcessor()

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
        
        # Initialize progress tracking for this analysis
        analysis_progress[analysis_id] = {
            "progress": 0,
            "step": 0,
            "status": "initializing",
            "result": None
        }
        
        # Handle URL-based analysis
        if request.json and 'url' in request.json:
            video_url = request.json.get('url')
            if not video_url:
                return jsonify({"error": "URL is required"}), 400
            
            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_url,
                args=(analysis_id, video_url)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "analysis_id": analysis_id,
                "status": "processing",
                "message": "Analysis started successfully. Check progress with the progress endpoint."
            })
            
        # Handle file upload analysis
        elif 'file' in request.files:
            file = request.files['file']
            if not file:
                return jsonify({"error": "No file selected"}), 400
                
            # Save the uploaded file temporarily
            temp_path = f"temp_video_{analysis_id}.mp4"
            file.save(temp_path)
            
            # Start analysis in background thread
            thread = threading.Thread(
                target=process_unified_analysis_file,
                args=(analysis_id, temp_path, file.filename)
            )
            thread.daemon = True
            thread.start()
            
            return jsonify({
                "analysis_id": analysis_id,
                "status": "processing",
                "message": "Analysis started successfully. Check progress with the progress endpoint."
            })
            
        else:
            return jsonify({"error": "Either URL or file must be provided"}), 400
            
    except Exception as e:
        print(f"Error in analyze_unified: {e}")
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

def process_unified_analysis_url(analysis_id, video_url):
    """Process a URL-based analysis in the background and update progress."""
    try:
        update_analysis_progress(analysis_id, 0, 0, "downloading")
        
        # 1. Download the video
        local_filename = f"temp_video_{analysis_id}.mp4"
        local_path = download_video_with_ytdlp(video_url, output_path=local_filename)
        update_analysis_progress(analysis_id, 12, 1, "uploading")
        
        # 2. Upload to S3
        s3_object_key = f"videos/{os.path.basename(local_path)}"
        s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
        update_analysis_progress(analysis_id, 25, 2, "running_clarifai")
        
        # 3. Run ClarifAI analysis
        clarifai_result = analyze_video_multi_model(s3_video_url, sample_ms=125)
        update_analysis_progress(analysis_id, 50, 3, "processing_gemini")
        
        # 4. Run Gemini analysis
        initial_analysis = analyze_video_output(clarifai_result)
        update_analysis_progress(analysis_id, 75, 5, "generating_structured_output")
        
        # 5. Create structured analysis
        unified_result = process_analysis(initial_analysis)
        
        # 6. Store the result
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "video_url": video_url,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"]
            },
            **unified_result
        }
        
        # Add to analyses list
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "video_url": video_url,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
            },
            "analysis_data": result_with_metadata
        })
        
        # Update progress to completed
        update_analysis_progress(analysis_id, 100, 7, "completed", result_with_metadata)
        
        # Clean up temp file
        if os.path.exists(local_path):
            os.remove(local_path)
            
    except Exception as e:
        print(f"Error processing URL analysis: {e}")
        update_analysis_progress(analysis_id, 0, 0, "error", {"error": str(e)})
        
        # Clean up temp file on error
        local_path = f"temp_video_{analysis_id}.mp4"
        if os.path.exists(local_path):
            os.remove(local_path)

def process_unified_analysis_file(analysis_id, file_path, filename):
    """Process a file-based analysis in the background and update progress."""
    try:
        update_analysis_progress(analysis_id, 10, 0, "preparing")
        
        # 1. Upload to S3
        s3_object_key = f"videos/{os.path.basename(file_path)}"
        s3_video_url = upload_to_s3(file_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
        update_analysis_progress(analysis_id, 25, 2, "running_clarifai")
        
        # 2. Run ClarifAI analysis
        clarifai_result = analyze_video_multi_model(s3_video_url, sample_ms=125)
        update_analysis_progress(analysis_id, 50, 3, "processing_gemini")
        
        # 3. Run Gemini analysis
        initial_analysis = analyze_video_output(clarifai_result)
        update_analysis_progress(analysis_id, 75, 5, "generating_structured_output")
        
        # 4. Create structured analysis
        unified_result = process_analysis(initial_analysis)
        
        # 5. Store the result
        result_with_metadata = {
            "metadata": {
                "id": analysis_id,
                "filename": filename,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                "analysis_sources": ["Gemini", "ClarifAI"]
            },
            **unified_result
        }
        
        # Add to analyses list
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "filename": filename,
                "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M")
            },
            "analysis_data": result_with_metadata
        })
        
        # Update progress to completed
        update_analysis_progress(analysis_id, 100, 7, "completed", result_with_metadata)
        
        # Clean up temp file
        if os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        print(f"Error processing file analysis: {e}")
        update_analysis_progress(analysis_id, 0, 0, "error", {"error": str(e)})
        
        # Clean up temp file on error
        if os.path.exists(file_path):
            os.remove(file_path)

def update_analysis_progress(analysis_id, progress, step, status, result=None):
    """Update the progress tracking for an analysis."""
    if analysis_id in analysis_progress:
        analysis_progress[analysis_id]["progress"] = progress
        analysis_progress[analysis_id]["step"] = step
        analysis_progress[analysis_id]["status"] = status
        if result:
            analysis_progress[analysis_id]["result"] = result

if __name__ == '__main__':
    app.run(debug=True, port=5000) 
