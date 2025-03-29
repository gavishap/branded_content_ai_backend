from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from narrative_analyzer import analyze_video_with_gemini
import uuid
from datetime import datetime
from dashboard_processor import DashboardProcessor
import time

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

if __name__ == '__main__':
    app.run(debug=True, port=5000) 
