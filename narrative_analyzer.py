import os
import time
import json
import re
from typing import List, Dict, Any, Union
from google import genai
from google.genai import types
from pathlib import Path
from dotenv import load_dotenv
import random

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
    """Waits for the given files to be active."""
    print("Waiting for file processing...")
    max_attempts = 6  # Reduced to 1 minute max (6 attempts * 10 seconds)
    attempt = 0
    
    for file in files:
        while attempt < max_attempts:
            try:
                # Get file status directly from the file object
                if file.state == "ACTIVE":
                    print("\nFile is active!")
                    return
                elif file.state == "FAILED":
                    raise Exception(f"File {file.name} failed to process")
                
                print(".", end="", flush=True)
                time.sleep(10)
                attempt += 1
                
                # Refresh the file status using the correct method
                if attempt % 2 == 0:  # Check more frequently
                    file = client.get_file(name=file.name)
                    
            except Exception as e:
                print(f"\nError checking file status: {str(e)}")
                raise Exception(f"File processing error: {str(e)}")
    
    raise Exception("File processing timed out after 1 minute")

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
(there are just example scores, i need u to give ur own)
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
            "Incorporate more dynamic transitions",
            "Optimize thumbnail with clear value proposition"
        ]
    },
    "Demographic Analysis": {
        "Gender Distribution": {
            "male": 60.5,
            "female": 39.5
        },
        "Age Distribution": {
            "0-17": 5.0,
            "18-24": 25.0,
            "25-34": 40.0,
            "35-44": 20.0,
            "45-64": 8.0,
            "65+": 2.0
        },
        "Ethnicity Distribution": {
            "caucasian": 45.0,
            "asian": 25.0,
            "hispanic": 15.0,
            "black": 12.0,
            "middle_eastern": 3.0
        },
        "Representation Quality": "The video shows a moderately diverse range of people across different demographics, with somewhat balanced gender representation and moderate ethnic diversity."
    },
    "Transcription": {
        "Full Text": "Complete transcription of all spoken words in the video",
        "Subtitle Coverage": {
            "Percentage": "85%",
            "Missing Segments": [
                {"start": "1:20", "end": "1:45"},
                {"start": "3:15", "end": "3:30"}
            ],
            "Quality Score": "90",
            "Issues": [
                "Some background noise interference",
                "Unclear pronunciation at 2:15"
            ]
        }
    },
    "Visual Analysis": {
        "Color Scheme": {
            "Dominant Colors": ["#HEXCODE1", "#HEXCODE2"],
            "Color Mood": "Warm/Cool/Neutral description",
            "Saturation Level": "0-100 score with analysis",
            "Contrast Rating": "0-100 score with analysis",
            "Brand Color Alignment": "How well colors match brand identity"
        },
        "Editing Pace": {
            "Average Cuts Per Second": "e.g. 1 cut every 2.5 seconds",
            "Total Cut Count": "Approximate number",
            "Pacing Analysis": "Whether the editing rhythm enhances or detracts from content"
        },
        "Thumbnail Analysis": {
            "thumbnail_optimization": [
                "Use high contrast colors to stand out in feeds",
                "Include clear text overlay with value proposition",
                "Feature close-up of main subject/product",
                "Ensure readability at small sizes"
            ]
        }
    },
    "Product Analysis": {
        "Featured Products": [
            {
                "Name": "Product name",
                "Screen Time": "Duration in seconds",
                "Timestamp Ranges": ["0:00-0:15", "1:20-1:45"],
                "Presentation Quality": "How clearly product is shown/demonstrated"
            }
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
                "Overall": "This video has moderate viral potential, with strengths in visual quality but could improve in emotional impact.",
                "Scores": {
                    "Visuals": 82,
                    "Emotional_Impact": 65,
                    "Shareability": 78,
                    "Relatability": 70,
                    "Uniqueness": 68
                },
                "Reasoning": {
                    "Visuals": "Professional quality visuals with good lighting and composition score well, but lack the highly distinctive style seen in most viral content.",
                    "Emotional_Impact": "Limited emotional storytelling reduces the likelihood of deep audience connection needed for virality.",
                    "Shareability": "Content has clear value that viewers would want to share with specific interested parties.",
                    "Relatability": "The content speaks to common experiences but doesn't create the strong 'that's so me' moment that drives viral sharing.",
                    "Uniqueness": "While professionally executed, the approach follows familiar patterns seen in similar content."
                }
            },
            "Platform Recommendations": {
                "Instagram": "Optimize for mobile viewing with clear visuals",
                "TikTok": "Focus on trending sounds and quick hooks in first 3 seconds",
                "YouTube Shorts": "Include clear branding and calls to action"
            }
        }
    }
}

For the Demographic Analysis section:
- Gender Distribution: Analyze the gender presentation of people appearing in the video with percentage values. Only use male and female categories, with percentages that add up to 100%.
- Age Distribution: Categorize the approximate ages of people in the video across standard age ranges.
- Ethnicity Distribution: Estimate the ethnicity representation in the video.
- Representation Quality: Provide an assessment of overall demographic diversity and representation.

Ensure all demographic percentages are numerical values (not text descriptions) that add up to 100 for each category.

For the Viral Potential section, carefully evaluate each component on a scale of 0-100 based on established research:
- Visuals: Assess visual quality, composition, color psychology, and whether it stands out in a social feed
- Emotional_Impact: Evaluate how strongly it triggers emotions like joy, surprise, inspiration or outrage
- Shareability: Analyze why viewers would want to share this (social currency, practical value, etc.)
- Relatability: Measure how well it connects with audience experiences or aspirations
- Uniqueness: Assess how differentiated it is from similar content in the same category

Your detailed reasoning should be based on analysis of viral video trends and research but won't be shown to users.

IMPORTANT: Return ONLY the JSON object, no additional text or markdown formatting. Ensure all fields have detailed, specific descriptions rather than generic statements."""

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
            # Look for the full JSON pattern with both open and close braces
            pattern = r'\{[\s\S]*\}'
            json_match = re.search(pattern, response_text)
            if not json_match:
                raise ValueError("No JSON found in response")
            json_str = json_match.group()
        
        # Clean the JSON string before parsing
        json_str = clean_json_response(json_str)
        
        # Parse the JSON with more lenient settings
        data = json.loads(json_str, strict=False)
        
        # Validate required fields with more flexible approach
        required_fields = [
            "Performance Metrics.Attention Score",
            "Performance Metrics.Engagement Potential", 
            "Performance Metrics.Watch Time Retention",
            "Performance Metrics.Key Strengths",
            "Performance Metrics.Improvement Suggestions",
            "Detailed Analysis.In-depth Video Analysis.Hook",
            "Detailed Analysis.In-depth Video Analysis.Editing",
            "Detailed Analysis.In-depth Video Analysis.Tonality",
            "Demographic Analysis.Gender Distribution",
            "Demographic Analysis.Age Distribution",
            "Demographic Analysis.Ethnicity Distribution",
            "Demographic Analysis.Representation Quality"
        ]
        
        # Only check the fields that are essential
        for field in required_fields:
            parts = field.split('.')
            current = data
            for part in parts:
                if part not in current:
                    print(f"Warning: Missing field: {field}")
                    break
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

def wait_for_file_active(file, max_attempts=20, sleep_duration=3):
    """Wait for an uploaded file to become active before using it.
    
    Args:
        file: The uploaded file object
        max_attempts: Maximum number of attempts before giving up
        sleep_duration: Time to sleep between attempts in seconds
        
    Returns:
        The updated file object once active
    """
    print(f"Waiting for file {file.name} to become active...")
    
    for attempt in range(max_attempts):
        try:
            # Check file status by retrieving it again
            updated_file = client.files.get(name=file.name)
            
            # Print status information
            print(f"Attempt {attempt+1}/{max_attempts}: File state is {updated_file.state}")
            
            if updated_file.state == "ACTIVE":
                print(f"✓ File is now active! ({attempt+1} attempts)")
                return updated_file
                
            elif updated_file.state == "FAILED":
                raise Exception(f"File processing failed: {updated_file.state_message}")
                
            # If still processing, wait and try again
            print(f"Waiting {sleep_duration}s for file to become active...")
            time.sleep(sleep_duration)
            
        except Exception as e:
            print(f"Error checking file status: {e}")
            # Continue trying despite errors
            time.sleep(sleep_duration)
    
    # If we get here, we've exceeded max attempts
    raise Exception(f"Timed out waiting for file {file.name} to become active after {max_attempts} attempts")

def analyze_video_with_gemini(path_or_url, is_url_prompt=False, max_retries=3, initial_retry_delay=2):
    """Analyzes a video using Gemini 2.5 Pro with retry mechanism for server errors."""
    retries = 0
    retry_delay = initial_retry_delay
    
    while retries <= max_retries:
        try:
            print(f"\nStarting analysis with Gemini (Attempt {retries + 1}/{max_retries + 1}):")
            print(f"Input: {path_or_url}")
            print(f"Is URL analysis: {is_url_prompt}")

            model = "gemini-2.5-pro-exp-03-25"
            
            # For file analysis, we need to use the client.files.upload method
            if not is_url_prompt:
                print("\nProcessing file analysis using direct file upload...")
                try:
                    # Upload the file directly using client.files.upload
                    print(f"Uploading local file: {path_or_url}")
                    uploaded_file = client.files.upload(file=path_or_url)
                    print(f"Uploaded file as: {uploaded_file.uri}")
                    
                    # Wait for the file to become active before proceeding
                    active_file = wait_for_file_active(uploaded_file)
                    
                    # Now use the uploaded file URI
                    contents = [
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_uri(
                                    file_uri=active_file.uri,
                                    mime_type=active_file.mime_type,
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
                    
                    # Configure generation config
                    generate_content_config = types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                    
                    # Save the raw response to a file
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    raw_filename = f"raw_gemini_file_response_{timestamp}.txt"
                    
                    with open(raw_filename, "w", encoding="utf-8") as f:
                        f.write("=== Raw Gemini File Response ===\n\n")
                        
                        try:
                            # Use the generate_content_stream
                            print("Sending file analysis request to Gemini...")
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
                            error_msg = f"\n\nError during file generation: {str(e)}"
                            f.write(error_msg)
                            print(error_msg)
                            
                            # Check if this is a server error (500) that we should retry
                            if "500 INTERNAL" in str(e) and retries < max_retries:
                                retries += 1
                                actual_delay = retry_delay + (random.random() * 0.5)
                                print(f"\nServer error detected. Retrying in {actual_delay:.1f} seconds (attempt {retries}/{max_retries})...")
                                time.sleep(actual_delay)
                                # Exponential backoff for next retry
                                retry_delay = min(retry_delay * 2, 30)  # Cap at 30 seconds
                                continue
                        
                        f.write("\n\n=== End of File Response ===")
                    
                    print(f"\nSaved raw file response to: {raw_filename}")
                    
                    # Load the file and return its content
                    with open(raw_filename, "r", encoding="utf-8") as f:
                        raw_content = f.read()
                    
                    # Try to extract JSON from the raw content
                    try:
                        result = extract_json_from_response(raw_content)
                        if result:
                            print("Successfully extracted JSON response from file upload")
                            return result
                    except Exception as e:
                        # Check if this is a parsing error we should retry
                        if retries < max_retries:
                            retries += 1
                            actual_delay = retry_delay + (random.random() * 0.5)
                            print(f"\nJSON parsing error: {str(e)}. Retrying in {actual_delay:.1f} seconds (attempt {retries}/{max_retries})...")
                            time.sleep(actual_delay)
                            # Exponential backoff for next retry
                            retry_delay = min(retry_delay * 2, 30)
                            continue
                        else:
                            print(f"Error extracting JSON after {max_retries} retries: {str(e)}")
                            return {"error": f"Failed to extract JSON after {max_retries} retries: {str(e)}"}
                    
                    return {"error": "Failed to extract valid JSON from file response"}
                    
                except Exception as upload_error:
                    print(f"\nFile upload/processing failed: {str(upload_error)}")
                    raise
            elif is_url_prompt:
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
                
                # Configure generation config
                generate_content_config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                )

                # Save the raw response to a file
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                raw_filename = f"raw_gemini_url_response_{timestamp}.txt"
                
                with open(raw_filename, "w", encoding="utf-8") as f:
                    f.write("=== Raw Gemini URL Response ===\n\n")
                    
                    try:
                        # Use the generate_content_stream
                        print("Sending URL request to Gemini...")
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
                        error_msg = f"\n\nError during URL generation: {str(e)}"
                        f.write(error_msg)
                        print(error_msg)
                        
                        # Check if this is a server error (500) that we should retry
                        if "500 INTERNAL" in str(e) and retries < max_retries:
                            retries += 1
                            # Add some jitter to retry delay
                            actual_delay = retry_delay + (random.random() * 0.5)
                            print(f"\nServer error detected. Retrying in {actual_delay:.1f} seconds (attempt {retries}/{max_retries})...")
                            time.sleep(actual_delay)
                            # Exponential backoff for next retry
                            retry_delay = min(retry_delay * 2, 30)  # Cap at 30 seconds
                            continue
                    
                    f.write("\n\n=== End of URL Response ===")
                
                print(f"\nSaved raw URL response to: {raw_filename}")
                
                # Load the file and return its content
                with open(raw_filename, "r", encoding="utf-8") as f:
                    raw_content = f.read()
                
                # Try to extract JSON from the raw content
                try:
                    result = extract_json_from_response(raw_content)
                    if result:
                        print("Successfully extracted JSON response from URL")
                        return result
                except Exception as e:
                    # Check if this is a parsing error we should retry
                    if retries < max_retries:
                        retries += 1
                        # Add some jitter to retry delay
                        actual_delay = retry_delay + (random.random() * 0.5)
                        print(f"\nJSON parsing error: {str(e)}. Retrying in {actual_delay:.1f} seconds (attempt {retries}/{max_retries})...")
                        time.sleep(actual_delay)
                        # Exponential backoff for next retry
                        retry_delay = min(retry_delay * 2, 30)  # Cap at 30 seconds
                        continue
                    else:
                        print(f"Error extracting JSON after {max_retries} retries: {str(e)}")
                        return {"error": f"Failed to extract JSON after {max_retries} retries: {str(e)}"}
                
            # If we've reached here successfully, break the retry loop
            break
                
        except Exception as e:
            print(f"\nError in analyze_video_with_gemini: {str(e)}")
            
            # Check if we should retry
            if "500 INTERNAL" in str(e) and retries < max_retries:
                retries += 1
                # Add some jitter to retry delay
                actual_delay = retry_delay + (random.random() * 0.5)
                print(f"\nServer error detected. Retrying in {actual_delay:.1f} seconds (attempt {retries}/{max_retries})...")
                time.sleep(actual_delay)
                # Exponential backoff for next retry
                retry_delay = min(retry_delay * 2, 30)  # Cap at 30 seconds
            else:
                return {"error": str(e)}
    
    # If we've exhausted retries
    if retries >= max_retries:
        return {"error": f"Failed to get valid response after {max_retries} retries"}

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
        "Demographic Analysis": {
            "Gender Distribution": extract_demographics(text, r"Gender Distribution\"?\s*:\s*\{(.*?)\}"),
            "Age Distribution": extract_demographics(text, r"Age Distribution\"?\s*:\s*\{(.*?)\}"),
            "Ethnicity Distribution": extract_demographics(text, r"Ethnicity Distribution\"?\s*:\s*\{(.*?)\}"),
            "Representation Quality": extract_value(text, r"Representation Quality\"?\s*:\s*\"([^\"]+)")
        },
        "Detailed Analysis": {
            "In-depth Video Analysis": {
                "Hook": extract_value(text, r"Hook\"?\s*:\s*\"([^\"]+)"),
                "Editing": extract_value(text, r"Editing\"?\s*:\s*\"([^\"]+)"),
                "Tonality": extract_value(text, r"Tonality\"?\s*:\s*\"([^\"]+)"),
                "Core Strengths": {
                    "Visuals": extract_value(text, r"Visuals\"?\s*:\s*\"([^\"]+)"),
                    "Content": extract_value(text, r"Content\"?\s*:\s*\"([^\"]+)"),
                    "Pacing": extract_value(text, r"Pacing\"?\s*:\s*\"([^\"]+)"),
                    "Value": extract_value(text, r"Value\"?\s*:\s*\"([^\"]+)"),
                    "CTA": extract_value(text, r"CTA\"?\s*:\s*\"([^\"]+)")
                },
                "Viral Potential": {
                    "Overall": extract_value(text, r"Overall\"?\s*:\s*\"([^\"]+)"),
                    "Scores": {
                        "Visuals": extract_value(text, r"Visuals\"?\s*:\s*(\d+)"),
                        "Emotional_Impact": extract_value(text, r"Emotional_Impact\"?\s*:\s*(\d+)"),
                        "Shareability": extract_value(text, r"Shareability\"?\s*:\s*(\d+)"),
                        "Relatability": extract_value(text, r"Relatability\"?\s*:\s*(\d+)"),
                        "Uniqueness": extract_value(text, r"Uniqueness\"?\s*:\s*(\d+)")
                    }
                },
                "Platform Recommendations": {
                    "Instagram": extract_value(text, r"Instagram\"?\s*:\s*\"([^\"]+)"),
                    "TikTok": extract_value(text, r"TikTok\"?\s*:\s*\"([^\"]+)"),
                    "YouTube Shorts": extract_value(text, r"YouTube Shorts\"?\s*:\s*\"([^\"]+)")
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

def extract_demographics(text, pattern):
    """Extract demographic distribution using regex."""
    match = re.search(pattern, text)
    if not match:
        return {}
    
    # Get the content inside the curly braces
    content = match.group(1)
    
    # Find all key-value pairs
    pairs = re.findall(r'\"?([\w\s\-\+]+)\"?\s*:\s*\"?(\d+(?:\.\d+)?)\"?', content)
    
    # Convert to a dictionary
    result = {}
    for key, value in pairs:
        key = key.strip().strip('"')
        try:
            # Try to convert to float first, then int if there's no decimal part
            float_val = float(value)
            result[key] = float_val
        except ValueError:
            # If conversion fails, keep original string
            result[key] = value
    
    return result

# Test function for development
def test_analysis(file_path=None):
    try:
        # Use provided file path or default test file
        if not file_path:
            # Default test file
            file_path = "tesla.mp4"
            
        if not os.path.exists(file_path):
            print(f"Error: Video file '{file_path}' not found")
            return
            
        print(f"Analyzing video using direct file upload: {file_path}")
        analysis = analyze_video_with_gemini(file_path, is_url_prompt=False)
        
        # Pretty print the results
        print("\nAnalysis Results:")
        if "error" in analysis:
            print(f"Analysis Error: {analysis['error']}")
        else:
            # Save the results to a JSON file for inspection
            results_file = f"analysis_results_{time.strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, "w", encoding="utf-8") as f:
                json.dump(analysis, f, indent=2)
            print(f"Analysis results saved to: {results_file}")
            
            # Print a brief summary
            if "analysis" in analysis:
                print("\nAnalysis Summary:")
                
                # Extract performance metrics
                performance = analysis["analysis"].get("Performance Metrics", {})
                if performance:
                    print(f"Attention Score: {performance.get('Attention Score', 'N/A')}")
                    print(f"Engagement Potential: {performance.get('Engagement Potential', 'N/A')}")
                    print(f"Watch Time Retention: {performance.get('Watch Time Retention', 'N/A')}")
                    
                    # Print key strengths
                    strengths = performance.get("Key Strengths", [])
                    if strengths:
                        print("\nKey Strengths:")
                        for i, strength in enumerate(strengths[:3], 1):
                            print(f"  {i}. {strength}")
                
                # Extract demographic information
                demographics = analysis["analysis"].get("Demographic Analysis", {})
                if demographics:
                    print("\nDemographic Analysis:")
                    
                    # Gender distribution
                    gender_dist = demographics.get("Gender Distribution", {})
                    if gender_dist:
                        print("\nGender Distribution:")
                        for gender, percentage in gender_dist.items():
                            print(f"  {gender}: {percentage}%")
                    
                    # Age distribution
                    age_dist = demographics.get("Age Distribution", {})
                    if age_dist:
                        print("\nAge Distribution:")
                        for age_range, percentage in age_dist.items():
                            print(f"  {age_range}: {percentage}%")
                    
                    # Ethnicity distribution
                    ethnicity_dist = demographics.get("Ethnicity Distribution", {})
                    if ethnicity_dist:
                        print("\nEthnicity Distribution:")
                        for ethnicity, percentage in ethnicity_dist.items():
                            print(f"  {ethnicity}: {percentage}%")
                    
                    # Representation quality
                    representation = demographics.get("Representation Quality", "")
                    if representation:
                        print(f"\nRepresentation Quality: {representation}")
        
    except Exception as e:
        print(f"Analysis Error: {str(e)}")
        import traceback
        print("\nFull error traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    # Check if a file path is provided as a command-line argument
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        print(f"Using provided file: {test_file}")
        test_analysis(test_file)
    else:
        print("No file specified, using default test file")
        test_analysis() 
