import os
import json
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import glob
import re

# Load environment variables
load_dotenv()

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is not set")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

def validate_analysis_data(raw_analysis: str) -> bool:
    """Validate that the raw analysis contains all required sections."""
    required_sections = [
        "Overview of Content",
        "Demographic Representation", 
        "Emotional Tone and Expression",
        "Quantified Performance Metrics",
        "Predicted Audience Fit",
        "Recommendations for Optimization"
    ]
    
    for section in required_sections:
        if section not in raw_analysis:
            print(f"Missing required section: {section}")
            return False
    return True

def extract_metrics(raw_analysis: str) -> Dict[str, Any]:
    """Extract metrics from the raw analysis text."""
    metrics = {}
    
    # Extract scores from the Quantified Performance Metrics section
    metrics_section = raw_analysis.split("## Quantified Performance Metrics")[1].split("##")[0]
    
    # Extract main scores
    score_lines = metrics_section.split("\n")
    for line in score_lines:
        if "**" in line and ":" in line:
            metric_name = line.split("**")[1].split(":**")[0].strip()
            score = line.split(":**")[1].strip()
            if score.isdigit():
                metrics[metric_name] = int(score)
            elif score in ["Low", "Medium", "High"]:
                metrics[metric_name] = score
    
    # Extract audience match scores
    audience_scores = {}
    for line in score_lines:
        if line.strip().startswith("-"):
            parts = line.strip("- ").split(":")
            if len(parts) == 2:
                audience = parts[0].strip()
                score = parts[1].strip()
                if score.isdigit():
                    audience_scores[audience] = int(score)
    
    if audience_scores:
        metrics["audience_match_scores"] = audience_scores
    
    return metrics

def generate_structured_output(raw_analysis: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Generate structured output using Gemini."""
    try:
        # First, let's try to generate a more concise prompt
        structured_prompt = """You are a JSON generator. Your task is to convert the provided analysis into a valid JSON object.
        
        Rules:
        1. Return ONLY the JSON object, nothing else
        2. Do not include any markdown formatting
        3. Do not include any explanations
        4. Ensure all JSON syntax is correct
        5. Use the exact structure provided below
        6. ALWAYS use numerical values for demographic data (not text like "high" or "medium")

        JSON Structure:
        {
        "overview": {"content_summary": "", "key_themes": [], "setting": ""},
        "demographics": {"age_distribution": {}, "gender_distribution": {}, "ethnicity_distribution": {}, "representation_quality": ""},
        "emotional_analysis": {"dominant_emotions": [], "emotional_arc": "", "tone": "", "emotional_resonance_score": 50, "insights": ""},
        "performance_metrics": {
        "engagement_score": 0,
        "ctr_potential": 0,
        "shareability": 0,
        "retention_score": 0,
        "hook_score": 0,
        "emotional_impact": 0,
        "virality_index": "",
        "representation_index": 0,
        "audience_match_scores": {}
        },
        "audience_fit": {"primary_audience": "", "secondary_audiences": [], "platform_recommendations": [], "platform_fit": {}},
        "optimization_recommendations": {
        "emotional_impact": [],
        "visual_enhancements": [],
        "representation": [],
        "audience_targeting": [],
        "thumbnail_optimization": [],
        "engagement_triggers": []
        },
        "content_quality": {
          "visual_elements": {
            "score": 50,
            "confidence": "Medium",
            "strengths": [],
            "improvement_areas": [],
            "color_scheme": {
              "dominant_colors": [],
              "color_mood": "",
              "saturation_level": 50,
              "contrast_rating": 50
            }
          },
          "audio_elements": {
            "score": 50,
            "confidence": "Medium",
            "strengths": [],
            "improvement_areas": []
          },
          "narrative_structure": {
            "score": 50,
            "confidence": "Medium",
            "strengths": [],
            "improvement_areas": []
          },
          "pacing_and_flow": {
            "score": 50,
            "confidence": "Medium",
            "insights": "",
            "editing_pace": {
              "average_cuts_per_second": 0,
              "total_cut_count": 0,
              "pacing_analysis": ""
            }
          }
        },
        "contradiction_analysis": []
        }

        Analysis to convert:
            {raw_analysis}

        IMPORTANT: For all demographic distribution values, use only numerical data (percentages). For example:
        "demographics": {
            "age_distribution": {
                "20-29": 60.3,
                "30-39": 47.0
            },
            "gender_distribution": {
                "male": 57.7,
                "female": 42.3
            },
            "ethnicity_distribution": {
                "Southeast Asian": 45.0,
                "Black": 30.8,
                "Middle Eastern": 15.0,
                "White": 5.0,
                "Hispanic/Latino": 4.2
            }
        }
        
        FOCUS ON THESE ADDITIONAL OUTPUTS:
        1. For content_quality, carefully extract:
           - Visual elements information including colors, lighting, composition
           - Audio elements including music, clarity, background noise
           - Narrative structure and storytelling approach
           - Pacing analysis including scene transitions and editing rhythm

        2. For emotional_analysis, provide:
           - Specific emotions detected (joy, sadness, surprise, etc.)
           - The emotional journey through the video
           - Estimated emotional impact score (0-100)
           - Detailed insights on how emotions affect audience engagement

        3. For contradiction_analysis, document any contradictions in the analysis (e.g., conflicting emotions or demographic interpretations)
        
        Remember: Return ONLY the JSON object, no other text."""

        print("Generating content from model...")
        
        # Configure the model for more consistent output
        model.temperature = 0.1
        model.top_p = 0.1
        model.top_k = 16
        
        # Generate the response
        complete_prompt = structured_prompt.replace("{raw_analysis}", raw_analysis)
        response = model.generate_content(complete_prompt)
        
        if not response.text:
            raise ValueError("No response generated from model")
            
        response_text = response.text
        
        # Save raw response for debugging
        print("Saving raw response...")
        os.makedirs('debug', exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = f"debug/raw_response_{timestamp}.txt"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(str(response_text))
        print(f"Raw response saved to: {debug_file}")

        # Clean the response text
        print("Cleaning response text...")
        response_text = response_text.strip()
        
        # Try to parse the response as JSON
        try:
            # First, try direct JSON parsing
            structured_data = json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract JSON from markdown
            json_blocks = re.findall(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_blocks:
                print("Found JSON blocks in response")
                try:
                    structured_data = json.loads(json_blocks[0])
                except json.JSONDecodeError:
                    print("Failed to parse JSON from blocks")
                    raise
            else:
                # Try to find a JSON-like structure
                print("Looking for JSON pattern in response")
                json_pattern = r'\{[\s\S]*\}'
                json_match = re.search(json_pattern, response_text)
                if json_match:
                    try:
                        structured_data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        print("Failed to parse JSON from pattern match")
                        raise
                else:
                    print("No JSON pattern found in response")
                    raise ValueError("No valid JSON found in response")

        print("JSON parsed successfully")

        # Add metadata
        structured_data["metadata"] = {
            "timestamp": datetime.now().isoformat(),
            "total_frames": metadata.get("total_frames", 0),
            "models_used": metadata.get("models_used", []),
            "sample_rate": metadata.get("sample_rate", 0)
        }

        return structured_data

    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        print("Raw response:")
        if 'response_text' in locals():
            print(response_text)
        raise

    except Exception as e:
        print(f"Error in generate_structured_output: {e}")
        print("Raw response:")
        if 'response_text' in locals():
            print(response_text)
        raise

def save_structured_analysis(structured_data: Dict[str, Any]) -> str:
    """Save the structured analysis to a file."""
    try:
        # Create structured_analysis directory if it doesn't exist
        os.makedirs('structured_analysis', exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"structured_analysis/analysis_{timestamp}.json"
        
        # Save the result
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, indent=2)
            
        print(f"Structured analysis saved to: {filename}")
        return filename
        
    except Exception as e:
        print(f"Error saving structured analysis: {e}")
        raise

def validate_demographic_data(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix demographic data to ensure all values are numerical.
    
    Args:
        structured_data: The structured analysis data
        
    Returns:
        Dict with validated/fixed demographic data
    """
    if not structured_data or "demographics" not in structured_data:
        print("No demographics data found to validate")
        return structured_data
    
    demographics = structured_data["demographics"]
    distributions = ["age_distribution", "gender_distribution", "ethnicity_distribution"]
    
    text_value_mappings = {
        "high": 80.0,
        "majority": 75.0,
        "predominant": 85.0,
        "strong": 70.0,
        "substantial": 65.0,
        "notable": 50.0,
        "medium": 50.0,
        "moderate": 40.0,
        "some": 30.0,
        "present": 25.0,
        "low": 20.0,
        "minimal": 10.0,
        "trace": 5.0
    }
    
    for dist_key in distributions:
        if dist_key in demographics:
            distribution = demographics[dist_key]
            
            # Skip if already empty or not a dictionary
            if not isinstance(distribution, dict) or not distribution:
                # If it's not a dict (e.g., None or a string), replace with empty dict
                demographics[dist_key] = {}
                continue

            fixed_distribution = {}
            # Check if the only key is 'needs_validation'
            if list(distribution.keys()) == ['needs_validation'] and distribution['needs_validation'] is True:
                 print(f"Warning: Demographic distribution '{dist_key}' contains only 'needs_validation'. Setting to empty.")
                 demographics[dist_key] = {}
                 continue

            for demo_key, value in distribution.items():
                # If value is already a number, ensure it's a float
                if isinstance(value, (int, float)):
                    fixed_distribution[demo_key] = float(value)
                # If value is a string
                elif isinstance(value, str):
                    if value.replace('.', '', 1).isdigit():
                        # It's a numeric string, convert to float
                        fixed_distribution[demo_key] = float(value)
                    else:
                        # It's a text value, map it to a number
                        lowercase_value = value.lower().strip()
                        if lowercase_value in text_value_mappings:
                            fixed_distribution[demo_key] = text_value_mappings[lowercase_value]
                        else:
                            # Default value if no mapping found or unhandled string
                            print(f"Warning: Converting unmapped/unhandled text value '{value}' in '{dist_key}' to default value 0.0")
                            fixed_distribution[demo_key] = 0.0
                # Handle boolean or other unexpected types
                else:
                    print(f"Warning: Converting non-numerical/non-string value '{value}' (type: {type(value)}) in '{dist_key}' to default value 0.0")
                    fixed_distribution[demo_key] = 0.0

            # Replace with fixed distribution
            demographics[dist_key] = fixed_distribution

    # Update the structured data with fixed demographics
    structured_data["demographics"] = demographics
    print("Demographics data validated and fixed if needed")
    return structured_data

def process_analysis(raw_analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """Main function to process the raw analysis into structured data."""
    try:
        # Validate the raw analysis
        if not validate_analysis_data(raw_analysis_result["raw_analysis"]):
            raise ValueError("Raw analysis missing required sections")
        
        # Generate structured output
        structured_data = generate_structured_output(
            raw_analysis_result["raw_analysis"],
            raw_analysis_result["metadata"]
        )
        
        # Validate and fix demographic data
        structured_data = validate_demographic_data(structured_data)
        
        # Save the structured analysis
        save_structured_analysis(structured_data)
        
        return structured_data
        
    except Exception as e:
        print(f"Error processing analysis: {e}")
        raise

def test_with_existing_analysis():
    """Test the structured analysis using an existing analysis file."""
    try:
        # Find the most recent analysis file
        analysis_files = glob.glob('analysis_results/analysis_*.json')
        if not analysis_files:
            print("No analysis files found in analysis_results directory")
            return
        
        # Sort by modification time and get the most recent
        latest_file = max(analysis_files, key=os.path.getmtime)
        print(f"Using analysis file: {latest_file}")
        
        # Load the analysis file
        with open(latest_file, 'r', encoding='utf-8') as f:
            raw_analysis_result = json.load(f)
        
        # Process the analysis
        print("\n--- Generating Structured Analysis ---")
        structured_result = process_analysis(raw_analysis_result)
        print("--- Structured Analysis Complete ---")
        print("Structured analysis has been saved and is ready for frontend use")
        
    except Exception as e:
        print(f"Error in test: {e}")

if __name__ == "__main__":
    test_with_existing_analysis()
