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

def _build_analysis_prompt(video_url: str, is_url: bool = True, is_url_prompt: bool = None) -> str:
    """Build the prompt for the video analysis."""
    
    # For backward compatibility - if is_url_prompt is provided, use it instead
    if is_url_prompt is not None:
        is_url = is_url_prompt
    
    # Define the JSON structure template separately to avoid nesting issues
    json_structure = '''{
  "analysis": {
    "Content Analysis": {
      "Video Format": "",
      "Setting": "",
      "Key Events": "",
      "Audio": "",
      "Text/Graphics": ""
    },
    "Visual Analysis": {
      "Color Palette": "",
      "Shot Types": "",
      "Lighting": "",
      "Visual Style": "",
      "Visual Quality": ""
    },
    "Product Analysis": {
      "Featured Product": "",
      "Brand Elements": "",
      "Product Presentation": "",
      "Value Proposition": "",
      "Call to Action": ""
    },
    "Performance Metrics": {
      "Attention Score": "",
      "Engagement Potential": "",
      "Watch Time Retention": "",
      "Key Strengths": [],
      "Improvement Suggestions": []
    },
    "Demographic Analysis": {
      "Total People Count": 0,
      "Gender Distribution": {
        "male": 0,
        "female": 0
      },
      "Age Distribution": {
        "0-17": 0,
        "18-24": 0,
        "25-34": 0,
        "35-44": 0,
        "45-64": 0,
        "65+": 0
      },
      "Ethnicity Distribution": {
        "caucasian": 0,
        "black": 0,
        "hispanic": 0,
        "asian": 0,
        "middle_eastern": 0
      },
      "Screen Time Distribution": {
        "main_subjects": 0,
        "secondary_subjects": 0,
        "background_appearances": 0
      },
      "Representation Quality": ""
    },
    "Detailed Analysis": {
        "In-depth Video Analysis": {
        "Hook": "",
        "Editing": "",
        "Tonality": "",
            "Viral Potential": {
          "Visuals": "",
          "Emotion": "",
          "Shareability": "",
          "Relatability": "",
          "Uniqueness": ""
        },
        "Core Strengths": {
          "Visuals": "",
          "Content": "",
          "Pacing": "",
          "Value": "",
          "CTA": ""
        }
      }
    }
  }
}'''
    
    prompt = ""
    if is_url:
        prompt = f"""Analyze this video: {video_url}

Your task is to provide a comprehensive analysis of this video advertisement. 
Focus on its characteristics, appeal, and marketing effectiveness.

Break down your analysis into these sections:
1. Content Analysis: Briefly describe what's happening in the video
2. Visual Analysis: Describe the predominant colors, shot types, lighting, and visual style
3. Product Analysis: Identify the featured product or service and how it's presented
4. Performance Metrics Prediction: Provide potential scores for attention, engagement, and retention
5. Demographic Analysis: Analyze the demographic representation in the video
6. Detailed Observations: Provide specific insights across multiple dimensions

For the Content Analysis section:
- Video Format: Identify what type of advertisement format this is.
- Setting: Describe where the video takes place. 
- Key Events: Summarize the main action or narrative arc.
- Audio: Describe the use of music, voice, sound effects.
- Text/Graphics: Note any on-screen text or graphics.

For the Visual Analysis section:
- Color Palette: Identify the main colors and their emotional impact.
- Shot Types: Describe the predominant shot types (close-ups, wide shots, etc.).
- Lighting: Analyze the lighting style and mood it creates.
- Visual Style: Comment on the overall aesthetic approach.
- Visual Quality: Assess the production value and visual clarity.

For the Product Analysis section:
- Featured Product: Name and describe the main product or service.
- Brand Elements: Identify logos, slogans, or distinctive brand markers.
- Product Presentation: How is the product showcased? Is it demonstrated?
- Value Proposition: What benefits or solutions does the product appear to offer?
- Call to Action: Is there a clear CTA? What is the viewer prompted to do?

For the Performance Metrics Prediction section:
- Attention Score (0-100): How likely is this to capture viewer attention in the first few seconds?
- Engagement Potential (0-100): How likely is this to maintain viewer interest throughout?
- Watch Time Retention (0-100%): What percentage of viewers would likely watch the entire video?
- Key Strengths: List 3-5 elements that would drive positive performance.
- Improvement Suggestions: List 3-5 potential changes that could enhance performance.

For the Demographic Analysis section:
- Total People Count: Count and provide the EXACT number of ALL people that appear in the video, even if just briefly or in the background.
- Gender Distribution: Analyze how much of the video's screen time is populated by male faces vs. female faces (not the count of people, but their presence throughout the video). Only use male and female categories, with percentages that add up to 100%.
- Age Distribution: Analyze the distribution of screen time across age groups throughout the video (0-17, 18-24, 25-34, 35-44, 45-64, 65+). Focus on how much of the video features each age group, not just counting individuals. Percentages should add up to 100%.
- Ethnicity Distribution: Analyze the distribution of screen time across different ethnicities throughout the video. Focus on specific ethnicities (caucasian, black, hispanic, asian, middle_eastern) without using mixed or other categories. Report what percentage of the video's screen time features each ethnicity. Percentages should add up to 100%.
- Screen Time Distribution: For videos with multiple people, calculate what percentage of total video screen time is given to main subjects, secondary subjects, and background appearances. Percentages should add up to 100%.
- Representation Quality: Provide an assessment of overall demographic diversity and representation.

For the Detailed Analysis section, include "In-depth Video Analysis" with these subsections:
- Hook: Analyze the opening seconds and how effectively they grab attention.
- Editing: Count the EXACT number of scene cuts/transitions in the video and calculate the average cuts per second. Describe the pacing, transitions, and overall editing style. For example "12 total cuts with approximately 0.5 cuts per second" or "8 total cuts with a cut every 3 seconds".
- Tonality: Describe the emotional tone and mood of the advertisement. Identify the dominant emotions (e.g., happiness, sadness, excitement) present in the video and assign an approximate percentage to each emotion (should add up to 100%).
- Viral Potential: Rate each aspect on a scale of 0-100:
  * Visuals: Are they striking, unique, or highly appealing?
  * Emotion: Does it evoke strong emotional responses?
  * Shareability: Would viewers want to share this content?
  * Relatability: How well would the target audience connect with this?
  * Uniqueness: How different is this from typical ads in its category?
- Core Strengths: Identify the strongest aspects in these categories:
  * Visuals: What visual elements stand out positively?
  * Content: What content elements are most compelling?
  * Pacing: How well is the timing and rhythm executed?
  * Value: How clearly is the value proposition conveyed?
  * CTA: How effectively is the call to action presented?

Organize your analysis to be detailed and insightful, while remaining objective. Use specific video timestamps and elements to support your observations.

Use JSON format for your response. Here's the structure:
{json_structure}

Ensure all demographic percentages add up to exactly 100% in each category. For Total People Count, provide an actual number, not a percentage.
"""
    else:
        prompt = f"""Analyze the previously uploaded video.

Your task is to provide a comprehensive analysis of this video advertisement. 
Focus on its characteristics, appeal, and marketing effectiveness.

Break down your analysis into these sections:
1. Content Analysis: Briefly describe what's happening in the video
2. Visual Analysis: Describe the predominant colors, shot types, lighting, and visual style
3. Product Analysis: Identify the featured product or service and how it's presented
4. Performance Metrics Prediction: Provide potential scores for attention, engagement, and retention
5. Demographic Analysis: Analyze the demographic representation in the video
6. Detailed Observations: Provide specific insights across multiple dimensions

For the Content Analysis section:
- Video Format: Identify what type of advertisement format this is.
- Setting: Describe where the video takes place. 
- Key Events: Summarize the main action or narrative arc.
- Audio: Describe the use of music, voice, sound effects.
- Text/Graphics: Note any on-screen text or graphics.

For the Visual Analysis section:
- Color Palette: Identify the main colors and their emotional impact.
- Shot Types: Describe the predominant shot types (close-ups, wide shots, etc.).
- Lighting: Analyze the lighting style and mood it creates.
- Visual Style: Comment on the overall aesthetic approach.
- Visual Quality: Assess the production value and visual clarity.

For the Product Analysis section:
- Featured Product: Name and describe the main product or service.
- Brand Elements: Identify logos, slogans, or distinctive brand markers.
- Product Presentation: How is the product showcased? Is it demonstrated?
- Value Proposition: What benefits or solutions does the product appear to offer?
- Call to Action: Is there a clear CTA? What is the viewer prompted to do?

For the Performance Metrics Prediction section:
- Attention Score (0-100): How likely is this to capture viewer attention in the first few seconds?
- Engagement Potential (0-100): How likely is this to maintain viewer interest throughout?
- Watch Time Retention (0-100%): What percentage of viewers would likely watch the entire video?
- Key Strengths: List 3-5 elements that would drive positive performance.
- Improvement Suggestions: List 3-5 potential changes that could enhance performance.

For the Demographic Analysis section:
- Total People Count: Count and provide the EXACT number of ALL people that appear in the video, even if just briefly or in the background.
- Gender Distribution: Analyze how much of the video's screen time is populated by male faces vs. female faces (not the count of people, but their presence throughout the video). Only use male and female categories, with percentages that add up to 100%.
- Age Distribution: Analyze the distribution of screen time across age groups throughout the video (0-17, 18-24, 25-34, 35-44, 45-64, 65+). Focus on how much of the video features each age group, not just counting individuals. Percentages should add up to 100%.
- Ethnicity Distribution: Analyze the distribution of screen time across different ethnicities throughout the video. Focus on specific ethnicities (caucasian, black, hispanic, asian, middle_eastern) without using mixed or other categories. Report what percentage of the video's screen time features each ethnicity. Percentages should add up to 100%.
- Screen Time Distribution: For videos with multiple people, calculate what percentage of total video screen time is given to main subjects, secondary subjects, and background appearances. Percentages should add up to 100%.
- Representation Quality: Provide an assessment of overall demographic diversity and representation.

For the Detailed Analysis section, include "In-depth Video Analysis" with these subsections:
- Hook: Analyze the opening seconds and how effectively they grab attention.
- Editing: Count the EXACT number of scene cuts/transitions in the video and calculate the average cuts per second. Describe the pacing, transitions, and overall editing style. For example "12 total cuts with approximately 0.5 cuts per second" or "8 total cuts with a cut every 3 seconds".
- Tonality: Describe the emotional tone and mood of the advertisement. Identify the dominant emotions (e.g., happiness, sadness, excitement) present in the video and assign an approximate percentage to each emotion (should add up to 100%).
- Viral Potential: Rate each aspect on a scale of 0-100:
  * Visuals: Are they striking, unique, or highly appealing?
  * Emotion: Does it evoke strong emotional responses?
  * Shareability: Would viewers want to share this content?
  * Relatability: How well would the target audience connect with this?
  * Uniqueness: How different is this from typical ads in its category?
- Core Strengths: Identify the strongest aspects in these categories:
  * Visuals: What visual elements stand out positively?
  * Content: What content elements are most compelling?
  * Pacing: How well is the timing and rhythm executed?
  * Value: How clearly is the value proposition conveyed?
  * CTA: How effectively is the call to action presented?

Organize your analysis to be detailed and insightful, while remaining objective. Use specific video timestamps and elements to support your observations.

Use JSON format for your response. Here's the structure:
{json_structure}

Ensure all demographic percentages add up to exactly 100% in each category. For Total People Count, provide an actual number, not a percentage.
"""
    return prompt

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
        
        # Extract emotion percentages from Tonality if available
        if "Detailed Analysis" in data and "In-depth Video Analysis" in data["Detailed Analysis"]:
            tonality = data["Detailed Analysis"]["In-depth Video Analysis"].get("Tonality", "")
            if tonality:
                # Extract emotion percentages from Tonality text
                emotion_percentages = extract_emotions(
                    tonality, 
                    r"(\d+%\s*[a-zA-Z]+|\b[a-zA-Z]+\s*\d+%)", 
                    r"([\w\s]+):\s*(\d+)%"
                )
                
                # Add emotion_percentages directly to the JSON
                if emotion_percentages and "emotional_analysis" not in data:
                    data["emotional_analysis"] = {
                        "dominant_emotions": list(emotion_percentages.keys()),
                        "emotion_percentages": emotion_percentages
                    }
                
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
                                types.Part.from_text(text=_build_analysis_prompt(path_or_url, is_url_prompt=False)),
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
                            types.Part.from_text(text=_build_analysis_prompt(path_or_url, is_url_prompt=True)),
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
                "Emotion Percentages": extract_emotions(text, r"Tonality\"?\s*:.*?(\d+%\s*[a-zA-Z]+|\b[a-zA-Z]+\s*\d+%)", r"Tonality\"?\s*:.*?([\w\s]+):\s*(\d+)%"),
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

def extract_emotions(text, pattern1, pattern2):
    """Extract emotion percentages from tonality section using regex."""
    emotions = {}
    
    # First method: Look for structured emotion: percentage pattern
    matches = re.findall(pattern2, text)
    if matches:
        for emotion, percentage in matches:
            emotions[emotion.strip()] = int(percentage)
        return emotions
    
    # Second method: Look for percentage and emotion mentions 
    matches = re.findall(pattern1, text)
    if matches:
        for match in matches:
            # Parse out the emotion and percentage
            if '%' in match:
                parts = match.split('%')
                if parts[0].strip().isdigit():
                    # Format: "50% happiness"
                    percentage = int(parts[0].strip())
                    emotion = parts[1].strip()
                else:
                    # Format: "happiness 50%"
                    percentage = int(parts[1].strip())
                    emotion = parts[0].strip()
                emotions[emotion] = percentage
    
    # If we found emotions but they don't add up to 100%, normalize them
    if emotions:
        total = sum(emotions.values())
        if total != 100:
            for emotion in emotions:
                emotions[emotion] = int(round((emotions[emotion] / total) * 100))
            # Adjust to ensure sum is exactly 100
            diff = 100 - sum(emotions.values())
            if diff != 0:
                # Add the difference to the largest emotion
                max_emotion = max(emotions, key=emotions.get)
                emotions[max_emotion] += diff
    
    return emotions

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
