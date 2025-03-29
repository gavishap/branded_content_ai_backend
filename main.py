from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from narrative_analyzer import analyze_video_with_gemini

app = Flask(__name__)
CORS(app)

# In-memory storage for analyses
analyses = []

@app.route('/api/analyses', methods=['GET'])
def get_analyses():
    return jsonify({"analyses": analyses})

@app.route('/api/analyze-url', methods=['POST'])
def analyze_url():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"error": "URL is required"}), 400
            
        url = data['url']
        print(f"\nReceived URL for analysis: {url}")
        
        # Analyze the video URL
        result = analyze_video_with_gemini(url, is_url_prompt=True)
        
        if "error" in result:
            return jsonify({"error": result["error"]}), 500
            
        # Store the analysis
        analysis_id = f"analysis_{len(analyses)}"
        analyses.append({
            "metadata": {
                "id": analysis_id,
                "video_name": url,
                "analyzed_date": "2024-03-30"  # You might want to use actual date
            },
            "dashboard_data": result
        })
            
        return jsonify({
            "analysis_id": analysis_id,
            "dashboard_data": result
        })
        
    except Exception as e:
        print(f"Error in analyze_url: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/analyze-file', methods=['POST'])
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
                
            # Store the analysis
            analysis_id = f"analysis_{len(analyses)}"
            analyses.append({
                "metadata": {
                    "id": analysis_id,
                    "video_name": file.filename,
                    "analyzed_date": "2024-03-30"  # You might want to use actual date
                },
                "dashboard_data": result
            })
                
            return jsonify({
                "analysis_id": analysis_id,
                "dashboard_data": result
            })
            
        finally:
            # Clean up the temporary file
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        print(f"Error in analyze_file: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000) 
