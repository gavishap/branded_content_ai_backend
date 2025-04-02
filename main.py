from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from narrative_analyzer import analyze_video_with_gemini
import uuid
from datetime import datetime
from dashboard_processor import DashboardProcessor
import time
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

# In-memory storage for analyses
analyses = []

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
        # Handle URL-based analysis
        if request.json and 'url' in request.json:
            video_url = request.json.get('url')
            if not video_url:
                return jsonify({"error": "URL is required"}), 400
                
            # Run the unified analysis
            print(f"\nStarting unified analysis for URL: {video_url}")
            unified_result = analyze_video_unified(video_url)
            
            # Create analysis ID
            analysis_id = str(uuid.uuid4())
            
            # Store the analysis
            analyses.append({
                "metadata": {
                    "id": analysis_id,
                    "video_name": "Unified Analysis - " + video_url.split('/')[-1],
                    "analyzed_date": datetime.now().strftime("%B %d, %Y %H:%M"),
                    "type": "unified"
                },
                "unified_data": unified_result
            })
                
            return jsonify({
                "analysis_id": analysis_id,
                "unified_data": unified_result
            })
        else:
            return jsonify({"error": "URL is required in the request body"}), 400
            
    except Exception as e:
        print(f"Error in unified analysis: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000) 
