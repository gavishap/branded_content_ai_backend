import os
import json
from typing import Dict, Any
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is not set")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

def load_prompt_template() -> str:
    """Load the prompt template from the structured prompt file."""
    try:
        with open('clarif_ai_structured_prompt.txt', 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error loading prompt template: {e}")
        raise

def prepare_analysis_data(clarifai_output: Dict[str, Any]) -> str:
    """Prepare the Clarifai output data in a format suitable for the prompt."""
    # Extract relevant data from the Clarifai output
    data = {
        "concept_distribution": clarifai_output.get("concepts", {}).get("concept_distribution_percent", {}),
        "emotion_breakdown": clarifai_output.get("faces", {}).get("attribute_distribution_percent", {}).get("sentiment", {}),
        "gender_breakdown": clarifai_output.get("faces", {}).get("attribute_distribution_percent", {}).get("gender", {}),
        "ethnicity_breakdown": clarifai_output.get("faces", {}).get("attribute_distribution_percent", {}).get("multiculturality", {}),
        "age_distribution": clarifai_output.get("faces", {}).get("attribute_distribution_percent", {}).get("age", {}),
        "objects_detected": clarifai_output.get("objects", {}).get("object_distribution_percent", {}),
        "celebrity_presence": next(iter(clarifai_output.get("celebrities", {}).get("celebrity_distribution_percent", {}).keys()), "None")
    }
    
    return json.dumps(data, indent=2)

def generate_analysis(clarifai_output: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured analysis using Gemini."""
    try:
        # Load the prompt template
        prompt_template = load_prompt_template()
        
        # Prepare the data
        analysis_data = prepare_analysis_data(clarifai_output)
        
        # Combine prompt and data
        full_prompt = f"{prompt_template}\n\nInput Data:\n{analysis_data}"
        
        # Generate response
        response = model.generate_content(full_prompt)
        
        # Parse the response into structured data
        # Note: You might need to adjust this parsing based on the actual response format
        analysis_result = {
            "timestamp": datetime.now().isoformat(),
            "raw_analysis": response.text,
            "metadata": {
                "total_frames": clarifai_output.get("video_summary", {}).get("total_frames_analyzed_approx", 0),
                "models_used": clarifai_output.get("video_summary", {}).get("analysis_models_succeeded", []),
                "sample_rate": clarifai_output.get("video_summary", {}).get("requested_sample_ms", 0)
            }
        }
        
        # Save the analysis result
        save_analysis_result(analysis_result)
        
        return analysis_result
        
    except Exception as e:
        print(f"Error generating analysis: {e}")
        raise

def save_analysis_result(analysis_result: Dict[str, Any]) -> None:
    """Save the analysis result to a file."""
    try:
        # Create analysis directory if it doesn't exist
        os.makedirs('analysis_results', exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"analysis_results/analysis_{timestamp}.json"
        
        # Save the result
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, indent=2)
            
        print(f"Analysis result saved to: {filename}")
        
    except Exception as e:
        print(f"Error saving analysis result: {e}")
        raise

def analyze_video_output(clarifai_output: Dict[str, Any]) -> Dict[str, Any]:
    """Main function to analyze video output from Clarifai."""
    try:
        return generate_analysis(clarifai_output)
    except Exception as e:
        print(f"Error in analyze_video_output: {e}")
        raise 
