import os
import time
import json
import re
from typing import List, Dict, Any, Union
from google import genai
from google.genai import types
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Load and configure API key
GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API_KEY not found in environment variables")

# Initialize Gemini client exactly like in test.py
client = genai.Client(
    api_key=GEMINI_API_KEY,
)

def upload_to_gemini(path, mime_type=None):
    """Uploads the given file to Gemini.
    """
    file = client.upload_file(path, mime_type=mime_type)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

def wait_for_files_active(files):
    """Waits for the given files to be active.
    """
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = client.get_file(name)
        while file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(10)
            file = client.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")
    print("...all files ready")
    print()

def get_video_mime_type(file_path: Union[str, Path]) -> str:
    """
    Determines the MIME type based on file extension.
    
    Args:
        file_path: Path to the video file
    
    Returns:
        str: MIME type for the video
    """
    extension = Path(file_path).suffix.lower()
    mime_types = {
        '.mp4': 'video/mp4',
        '.webm': 'video/webm',
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.mkv': 'video/x-matroska'
    }
    return mime_types.get(extension, 'video/mp4')

def clean_json_response(text):
    """Clean the response text to ensure valid JSON."""
    # Find JSON blocks in markdown code blocks
    json_blocks = re.findall(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    
    if json_blocks:
        # Combine multiple JSON blocks if they exist
        combined_json = {}
        for block in json_blocks:
            try:
                # Parse each block
                json_data = json.loads(block)
                # Merge into combined_json
                combined_json.update(json_data)
            except json.JSONDecodeError:
                continue
        
        if combined_json:
            return json.dumps(combined_json)
    
    # Fallback to original method if no valid JSON blocks found
    json_start = text.find('{')
    json_end = text.rfind('}')
    if json_start >= 0 and json_end >= 0:
        text = text[json_start:json_end + 1]
    
    # Fix common JSON formatting issues
    text = text.replace('\n', ' ')
    text = re.sub(r'(?<!\\)"(?!,|\s*}|\s*]|\s*:)', '\\"', text)  # Fix unescaped quotes
    text = re.sub(r',\s*([}\]])', r'\1', text)  # Remove trailing commas
    
    return text

def _build_analysis_prompt():
    """Builds the analysis prompt template."""
    return """Analyze this video and provide a structured performance prediction. Format your response as a single JSON object with this structure:

{
    "Performance Metrics": {
        "Attention Score": "85",
        "Engagement Potential": "90",
        "Watch Time Retention": "75%",
        "Key Strengths": [
            "Engaging presenter",
            "High-quality visuals",
            "Clear value proposition"
        ],
        "Improvement Suggestions": [
            "Add subtitles or captions",
            "Incorporate more dynamic transitions"
        ]
    },
    "Detailed Analysis": {
        "In-depth Video Analysis": {
            "Hook": "The video starts with a strong hook by showcasing the product immediately.",
            "Editing": "The editing style is smooth and well-paced, with good transitions.",
            "Tonality": "The presenter's voice is enthusiastic and confident.",
            "Core Strengths": {
                "Visuals": "High-quality footage with good lighting and composition",
                "Content": "Clear and informative presentation of features",
                "Pacing": "Well-balanced pacing that maintains viewer interest",
                "Value": "Strong value proposition that resonates with target audience",
                "CTA": "Clear call-to-action that encourages viewer response"
            },
            "Viral Potential": {
                "Visuals": "Visually appealing and attention-grabbing content",
                "Emotion": "Creates emotional connection through storytelling",
                "Shareability": "Content is highly shareable across platforms",
                "Relatability": "Connects well with target demographic",
                "Uniqueness": "Offers unique perspective or approach"
            }
        }
    }
}

IMPORTANT: Return ONLY the JSON object, no additional text or markdown formatting."""

def extract_json_from_response(response_text):
    """Extracts and validates JSON from the response text."""
    try:
        # First try to extract JSON from markdown code blocks
        json_blocks = re.findall(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_blocks:
            # Use the first JSON block found
            json_str = json_blocks[0]
        else:
            # Fallback to finding JSON object in plain text
            json_match = re.search(r'\{[\s\S]*?\}', response_text)
            if not json_match:
                raise ValueError("No JSON found in response")
            json_str = json_match.group()
        
        # Parse the JSON with more lenient settings
        data = json.loads(json_str, strict=False)
        
        # Validate required fields
        required_fields = [
            "Performance Metrics.Attention Score",
            "Performance Metrics.Engagement Potential", 
            "Performance Metrics.Watch Time Retention",
            "Performance Metrics.Key Strengths",
            "Performance Metrics.Improvement Suggestions",
            "Detailed Analysis.In-depth Video Analysis.Hook",
            "Detailed Analysis.In-depth Video Analysis.Editing",
            "Detailed Analysis.In-depth Video Analysis.Tonality",
            "Detailed Analysis.In-depth Video Analysis.Core Strengths",
            "Detailed Analysis.In-depth Video Analysis.Viral Potential"
        ]
        
        for field in required_fields:
            parts = field.split('.')
            current = data
            for part in parts:
                if part not in current:
                    raise ValueError(f"Missing required field: {field}")
                current = current[part]
                
        # Get the detailed text by removing the JSON block and any markdown formatting
        detailed_text = response_text
        for block in json_blocks:
            detailed_text = detailed_text.replace(f"```json{block}```", "")
        detailed_text = detailed_text.strip()
        
        return {
            "analysis": data,
            "detailed_text": detailed_text
        }
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {str(e)}")
        print(f"Attempted to parse: {json_str if 'json_str' in locals() else 'No JSON string found'}")
        # Try to extract structured data when JSON parsing fails
        try:
            return {
                "analysis": extract_structured_data(response_text),
                "detailed_text": response_text
            }
        except Exception as e2:
            raise ValueError(f"Invalid JSON in response: {str(e)}")
    except Exception as e:
        print(f"Error processing response: {str(e)}")
        print(f"Response text: {response_text}")
        raise ValueError(f"Error processing response: {str(e)}")

def analyze_video_with_gemini(path_or_url, is_url_prompt=False):
    """Analyzes a video using Gemini 2.5 Pro."""
    try:
        print(f"\nStarting analysis with Gemini:")
        print(f"Input: {path_or_url}")
        print(f"Is URL analysis: {is_url_prompt}")

        model = "gemini-2.5-pro-exp-03-25"

        if is_url_prompt:
            print("\nProcessing URL analysis...")
            # Format the request for URL
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=path_or_url,
                            mime_type="video/*",
                        ),
                    ],
                ),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=_build_analysis_prompt()),
                    ],
                ),
            ]
        else:
            print("\nProcessing file analysis...")
            # For files, use the file path directly
            mime_type = get_video_mime_type(path_or_url)
            # Upload the file using the correct method
            files = [
                client.files.upload(file=path_or_url),
            ]
            print(f"Uploaded file as: {files[0].uri}")
            
            # Format the request using the uploaded file
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=files[0].uri,
                            mime_type=mime_type,
                        ),
                    ],
                ),
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=_build_analysis_prompt()),
                    ],
                ),
            ]

        # Configure generation exactly as in test.py
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="application/json",
        )

        # Save the raw response to a file
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        raw_filename = f"raw_gemini_response_{timestamp}.txt"
        
        with open(raw_filename, "w", encoding="utf-8") as f:
            f.write("=== Raw Gemini Response ===\n\n")
            
            try:
                # Use the generate_content_stream exactly as in test.py
                print("Sending request to Gemini...")
                for chunk in client.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if chunk.text:
                        f.write(chunk.text)
                        print(chunk.text, end="")  # Print to console as well
                        f.flush()  # Make sure it's written immediately
            except Exception as e:
                error_msg = f"\n\nError during generation: {str(e)}"
                f.write(error_msg)
                print(error_msg)
            
            f.write("\n\n=== End of Response ===")
        
        print(f"\nSaved raw response to: {raw_filename}")
        
        # Let's also load the file and return its content as the result
        with open(raw_filename, "r", encoding="utf-8") as f:
            raw_content = f.read()
        
        # Try to extract JSON from the raw content
        try:
            result = extract_json_from_response(raw_content)
            if result:
                print("Successfully extracted JSON response from raw file")
                return result
        except Exception as e:
            print(f"Error extracting JSON: {str(e)}")
            return {"error": f"Failed to extract JSON: {str(e)}"}
            
        return {"error": "Failed to extract valid JSON from response"}
            
    except Exception as e:
        print(f"\nError in analyze_video_with_gemini: {str(e)}")
        return {"error": str(e)}

def extract_structured_data(text):
    """
    Extract structured data from the response when JSON parsing fails.
    Falls back to a more lenient parsing approach.
    """
    # Define the structure we expect
    structure = {
        "Performance Metrics": {
            "Attention Score": extract_value(text, r"Attention Score\"?\s*:\s*\"?(\d+)"),
            "Engagement Potential": extract_value(text, r"Engagement Potential\"?\s*:\s*\"?(\d+)"),
            "Watch Time Retention": extract_value(text, r"Watch Time Retention\"?\s*:\s*\"?(\d+)%?"),
            "Key Strengths": extract_list(text, r"Key Strengths\"?\s*:\s*\[(.*?)\]"),
            "Improvement Suggestions": extract_list(text, r"Improvement Suggestions\"?\s*:\s*\[(.*?)\]")
        },
        "Detailed Analysis": {
            "In-depth Video Analysis": {
                "Hook": extract_value(text, r"Hook\"?\s*:\s*\"([^\"]+)"),
                "Editing": extract_value(text, r"Editing\"?\s*:\s*\"([^\"]+)"),
                "Tonality of Voice": extract_value(text, r"Tonality of Voice\"?\s*:\s*\"([^\"]+)"),
                "Core Strengths on Social Media": {
                    "Visually Appealing": extract_value(text, r"Visually Appealing\"?\s*:\s*\"([^\"]+)"),
                    "Relatable Content": extract_value(text, r"Relatable Content\"?\s*:\s*\"([^\"]+)"),
                    "Length and Pacing": extract_value(text, r"Length and Pacing\"?\s*:\s*\"([^\"]+)"),
                    "Value Proposition": extract_value(text, r"Value Proposition\"?\s*:\s*\"([^\"]+)"),
                    "Call to Action": extract_value(text, r"Call to Action\"?\s*:\s*\"([^\"]+)")
                },
                "Viral Video Criteria": {
                    "Intriguing Visuals": extract_value(text, r"Intriguing Visuals\"?\s*:\s*\"([^\"]+)"),
                    "Emotional Connection": extract_value(text, r"Emotional Connection\"?\s*:\s*\"([^\"]+)"),
                    "Shareability": extract_value(text, r"Shareability\"?\s*:\s*\"([^\"]+)"),
                    "Relatability": extract_value(text, r"Relatability\"?\s*:\s*\"([^\"]+)"),
                    "Uniqueness": extract_value(text, r"Uniqueness\"?\s*:\s*\"([^\"]+)")
                }
            }
        }
    }
    
    return structure

def extract_value(text, pattern):
    """Extract a single value using regex."""
    match = re.search(pattern, text)
    return match.group(1) if match else ""

def extract_list(text, pattern):
    """Extract a list of values using regex."""
    match = re.search(pattern, text)
    if not match:
        return []
    
    items = match.group(1).split(',')
    return [item.strip().strip('"') for item in items if item.strip()]

# Update the test_analysis function to be synchronous
def test_analysis():
    try:
        # Test with Tesla video file
        file_path = "tesla.mp4"
        if not os.path.exists(file_path):
            print(f"Error: Video file '{file_path}' not found")
            return
            
        print(f"Analyzing video: {file_path}")
        analysis = analyze_video_with_gemini(file_path)
        
        # Pretty print the results
        print("\nAnalysis Results:")
        if "raw_response" in analysis:
            print("Warning: Returning raw response due to parsing error")
            print(analysis["raw_response"])
        else:
            # Print Performance Metrics
            print("\n=== Performance Metrics ===")
            metrics = analysis["Performance Metrics"]
            if isinstance(metrics, dict) and "Note" not in metrics:
                print(f"Attention Score: {metrics.get('Attention Score', 'N/A')}")
                print(f"Engagement Potential: {metrics.get('Engagement Potential', 'N/A')}")
                print(f"Watch Time Retention: {metrics.get('Watch Time Retention', 'N/A')}")
                
                if "Key Strengths" in metrics:
                    print("\nKey Strengths:")
                    for strength in metrics["Key Strengths"]:
                        print(f"- {strength}")
                
                if "Improvement Suggestions" in metrics:
                    print("\nImprovement Suggestions:")
                    for suggestion in metrics["Improvement Suggestions"]:
                        print(f"- {suggestion}")
            else:
                print(metrics.get("Note", "No metrics available"))
            
            # Print Detailed Analysis
            print("\n=== Detailed Analysis ===")
            detailed = analysis["Detailed Analysis"]
            if "In-depth Video Analysis" in detailed:
                analysis_data = detailed["In-depth Video Analysis"]
                if isinstance(analysis_data, dict) and "Note" not in analysis_data:
                    if "Hook" in analysis_data:
                        print(f"\nHook: {analysis_data['Hook']}")
                    if "Editing" in analysis_data:
                        print(f"\nEditing: {analysis_data['Editing']}")
                    if "Tonality of Voice" in analysis_data:
                        print(f"\nTonality of Voice: {analysis_data['Tonality of Voice']}")
                    
                    if "Viral Video Criteria" in analysis_data:
                        print("\nViral Video Criteria:")
                        for key, value in analysis_data["Viral Video Criteria"].items():
                            print(f"\n{key}: {value}")
                    
                    if "Overall Assessment" in analysis_data:
                        print(f"\nOverall Assessment: {analysis_data['Overall Assessment']}")
                else:
                    print(analysis_data.get("Note", "No detailed analysis available"))
            else:
                print("No detailed analysis available")
        
    except Exception as e:
        print(f"Analysis Error: {str(e)}")
        import traceback
        print("\nFull error traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_analysis()  # Remove asyncio.run since we're now synchronous 
