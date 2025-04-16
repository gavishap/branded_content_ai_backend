import os
import json
import time
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import concurrent.futures
from dotenv import load_dotenv
import google.generativeai as genai
import asyncio
import re
import io  # Import io for uploading string data

# Import necessary modules for both analysis pipelines
from inference_layer import analyze_video_output
from structured_analysis import process_analysis, validate_demographic_data
from clarif_ai_insights import analyze_video_multi_model, download_video_with_ytdlp, upload_to_s3
from s3_utils import S3_BUCKET_NAME, s3_client
try:
    from analyze_video import ensure_frontend_compatible_analysis
except ImportError:
    # If the module isn't available, define a simple pass-through function
    def ensure_frontend_compatible_analysis(analysis):
        return analysis

# Load environment variables
load_dotenv()

# Configure Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is not set")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')

# Create unified_analyses directory if it doesn't exist
os.makedirs('unified_analyses', exist_ok=True)

def run_analyses_in_parallel(video_url_or_path: str, progress_callback=None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run both analysis pipelines in parallel and return their results.
    
    Args:
        video_url_or_path: URL of the video or path to local video file
        progress_callback: Optional callback function to report progress
        
    Returns:
        Tuple containing (gemini_analysis, clarifai_structured_analysis)
    """
    gemini_analysis = None
    clarifai_structured_analysis = None
    gemini_error = None
    clarifai_error = None
    
    # Determine if we're dealing with a URL or local file
    is_url = video_url_or_path.startswith(('http://', 'https://', 's3://'))
    
    # Create a function for Gemini analysis pipeline
    def run_gemini_analysis():
        try:
            print("Starting Gemini analysis pipeline...")
            from narrative_analyzer import analyze_video_with_gemini
            
            # Determine if we have a URL or a local file path
            is_url = video_url_or_path.startswith(('http://', 'https://', 's3://'))
            
            print(f"Analyzing using Gemini: {'URL' if is_url else 'Local File'}")
            
            # Use the retry mechanism built into the function
            # Set is_url_prompt=True for URLs, False for file paths
            result = analyze_video_with_gemini(video_url_or_path, is_url_prompt=is_url, max_retries=3, initial_retry_delay=2)
            
            # Check if there was an error
            if "error" in result:
                print(f"Gemini analysis completed with error: {result['error']}")
                return result
                
            print("Gemini analysis pipeline completed successfully")
            return result
        except Exception as e:
            print(f"Error in Gemini analysis pipeline: {e}")
            return {"error": str(e)}
    
    # Create a function for ClarifAI analysis pipeline
    def run_clarifai_analysis():
        # For local files, we need to upload to S3 first
        s3_video_url = None
        local_path = None
        
        try:
            print("Starting ClarifAI analysis pipeline...")
            
            if is_url:
                # If it's a URL, download it first
                local_filename = "temp_video_" + os.path.basename(video_url_or_path).split('?')[0] + ".mp4"
                local_path = download_video_with_ytdlp(video_url_or_path, output_path=local_filename)
            else:
                # If it's a local file, use it directly
                local_path = video_url_or_path
                local_filename = os.path.basename(local_path)
            
            # Report download complete if applicable
            if is_url and progress_callback:
                progress_callback("downloading_complete", 20)
            
            # 2. Upload to S3
            if progress_callback:
                progress_callback("uploading_to_s3", 25)
            
            s3_object_key = f"videos/{os.path.basename(local_path)}"
            s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=s3_object_key)
            
            # 3. Analyze using ClarifAI models
            if progress_callback:
                progress_callback("clarifai_models_started", 30)
                
            clarifai_result = analyze_video_multi_model(s3_video_url, sample_ms=125)
            
            # 4. Generate initial analysis
            initial_analysis = analyze_video_output(clarifai_result)
            
            # 5. Generate structured analysis
            structured_result = process_analysis(initial_analysis)
            
            # Store S3 URL in the metadata
            if "metadata" not in structured_result:
                structured_result["metadata"] = {}
            structured_result["metadata"]["s3_video_url"] = s3_video_url
            
            # 6. Clean up local file if we downloaded it
            if is_url and local_path and os.path.exists(local_path):
                os.remove(local_path)
                
            print("ClarifAI analysis pipeline completed successfully")
            return structured_result
        except Exception as e:
            print(f"Error in ClarifAI analysis pipeline: {e}")
            
            # Clean up resources on error
            if is_url and local_path and os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except:
                    pass
                    
            return {"error": str(e)}
    
    # Run both analyses in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        gemini_future = executor.submit(run_gemini_analysis)
        clarifai_future = executor.submit(run_clarifai_analysis)
        
        # Wait for both to complete
        print("Waiting for both analysis pipelines to complete...")
        for future in concurrent.futures.as_completed([gemini_future, clarifai_future]):
            try:
                result = future.result()
                if future == gemini_future:
                    if isinstance(result, dict) and "error" in result:
                        gemini_error = result["error"]
                        print(f"Gemini analysis failed: {gemini_error}")
                    else:
                        gemini_analysis = result
                else:
                    if isinstance(result, dict) and "error" in result:
                        clarifai_error = result["error"]
                        print(f"ClarifAI analysis failed: {clarifai_error}")
                    else:
                        clarifai_structured_analysis = result
            except Exception as e:
                print(f"Error in analysis pipeline: {e}")
                if future == gemini_future:
                    gemini_error = str(e)
                else:
                    clarifai_error = str(e)
    
    # Handle the case where one or both analyses failed
    if gemini_analysis is None:
        print("Gemini analysis failed. Using fallback data structure.")
        gemini_analysis = {
            "analysis": {
                "Performance Metrics": {
                    "Attention Score": "75",
                    "Engagement Potential": "70",
                    "Watch Time Retention": "70%",
                    "Key Strengths": ["Video content"],
                    "Improvement Suggestions": ["Try again with a different video"]
                },
                "Detailed Analysis": {
                    "In-depth Video Analysis": {
                        "Hook": "Analysis not available",
                        "Editing": "Analysis not available",
                        "Tonality": "Analysis not available",
                        "Core Strengths": {
                            "Visuals": "Analysis not available",
                            "Content": "Analysis not available",
                            "Pacing": "Analysis not available",
                            "Value": "Analysis not available",
                            "CTA": "Analysis not available"
                        }
                    }
                }
            },
            "error": gemini_error,
            "timestamp": datetime.now().isoformat(),
            "id": "gemini_fallback",
            "video_url": video_url_or_path
        }
    
    if clarifai_structured_analysis is None:
        print("ClarifAI analysis failed. Using fallback data structure.")
        clarifai_structured_analysis = {
            "overview": {
                "content_summary": "Analysis not available due to an error",
                "key_themes": [],
                "setting": "Unknown"
            },
            "demographics": {
                "age_distribution": {},
                "gender_distribution": {},
                "ethnicity_distribution": {},
                "representation_quality": "Analysis not available"
            },
            "emotional_analysis": {
                "dominant_emotions": [],
                "emotional_arc": "Analysis not available",
                "tone": "Unknown"
            },
            "performance_metrics": {
                "engagement_score": 50,
                "ctr_potential": 50,
                "shareability": 50,
                "retention_score": 50,
                "virality_index": "Medium",
                "representation_index": 50,
                "audience_match_scores": {}
            },
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "error": clarifai_error
            }
        }
    
    return gemini_analysis, clarifai_structured_analysis

def extract_metrics_from_gemini(gemini_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant metrics from Gemini analysis format.
    """
    metrics = {}
    
    try:
        # Extract analysis data
        if "analysis" in gemini_analysis:
            analysis = gemini_analysis["analysis"]
            
            # Get performance metrics
            if "Performance Metrics" in analysis:
                perf_metrics = analysis["Performance Metrics"]
                metrics["performance"] = {
                    "attention_score": perf_metrics.get("Attention Score", "70"),
                    "engagement_potential": perf_metrics.get("Engagement Potential", "70"),
                    "watch_time_retention": perf_metrics.get("Watch Time Retention", "70%"),
                    "strengths": perf_metrics.get("Key Strengths", []),
                    "improvement_suggestions": perf_metrics.get("Improvement Suggestions", [])
                }
            
            # Get demographic data
            if "Demographic Analysis" in analysis:
                demographics = analysis["Demographic Analysis"]
                metrics["demographics"] = {
                    "gender_distribution": demographics.get("Gender Distribution", {}),
                    "age_distribution": demographics.get("Age Distribution", {}),
                    "ethnicity_distribution": demographics.get("Ethnicity Distribution", {}),
                    "representation_quality": demographics.get("Representation Quality", "")
                }
            
            # Get detailed analysis
            if "Detailed Analysis" in analysis and "In-depth Video Analysis" in analysis["Detailed Analysis"]:
                details = analysis["Detailed Analysis"]["In-depth Video Analysis"]
                metrics["content_details"] = {
                    "hook": details.get("Hook", ""),
                    "editing": details.get("Editing", ""),
                    "tonality": details.get("Tonality", "")
                }
                
                # Get core strengths
                if "Core Strengths" in details:
                    strengths = details["Core Strengths"]
                    metrics["core_strengths"] = {
                        "visuals": strengths.get("Visuals", ""),
                        "content": strengths.get("Content", ""),
                        "pacing": strengths.get("Pacing", ""),
                        "value": strengths.get("Value", ""),
                        "cta": strengths.get("CTA", "")
                    }
                
                # Get viral potential
                if "Viral Potential" in details:
                    viral = details["Viral Potential"]
                    metrics["viral_potential"] = {
                        "visuals": viral.get("Visuals", ""),
                        "emotion": viral.get("Emotion", ""),
                        "shareability": viral.get("Shareability", ""),
                        "relatability": viral.get("Relatability", ""),
                        "uniqueness": viral.get("Uniqueness", "")
                    }
    except Exception as e:
        print(f"Error extracting metrics from Gemini analysis: {e}")
    
    return metrics

def combine_analyses(gemini_analysis: Dict[str, Any], clarifai_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate the unification prompt and send to Gemini for processing.
    
    Args:
        gemini_analysis: Analysis from Gemini
        clarifai_analysis: Structured analysis from ClarifAI
        
    Returns:
        Combined analysis with validation
    """
    # Extract relevant metrics from both analyses
    gemini_metrics = extract_metrics_from_gemini(gemini_analysis)
    
    # Convert input analyses to properly formatted JSON strings
    gemini_json = json.dumps(gemini_analysis, ensure_ascii=False)
    clarifai_json = json.dumps(clarifai_analysis, ensure_ascii=False)
    
    # Create the prompt for the unification model
    unification_prompt = f"""
You are an expert AI video analyst specializing in synthesizing multiple analyses of video content.
You are being provided with two different AI analyses of the same video:

1. Standard Analysis (Gemini): Focuses on content, style, performance metrics, visual analysis, product analysis, viral potential, demographic analysis, and detailed observations.
2. Structured Analysis (ClarifAI): Focuses on demographic representation, emotional tone, visual elements, and audience fit.

# Your task:
Create a unified, comprehensive analysis that combines insights from both sources while resolving any contradictions.

# Guidelines:
1. CRITICAL: Compare corresponding metrics between the two analyses and reconcile any contradictions.
2. ESPECIALLY IMPORTANT: Compare demographic data (gender, age, ethnicity distributions) from both analyses and create a more accurate combined assessment.
3. When metrics differ significantly, add a confidence rating (Low/Medium/High) based on:
   - How much the analyses agree
   - The specificity of the observations
   - Internal consistency within each analysis
4. For contradictory insights, present both perspectives with your reconciliation.
5. Use facts from BOTH analyses to create more nuanced insights.
6. Make the unified output more detailed and useful than either input alone.
7. The output must be well-structured for display in dashboards with charts, graphs, and tables.
8. IMPORTANT: Incorporate ALL metrics and insights from both analyses without omitting any key information.

# Input Analysis 1 (Gemini):
```json
{gemini_json}
```

# Input Analysis 2 (ClarifAI Structured):
```json
{clarifai_json}
```

# Output Format:
You MUST respond using ONLY valid JSON in this EXACT structure. Ensure your output is parseable as valid JSON:

```json
{{
  "metadata": {{
    "timestamp": "ISO-formatted timestamp",
    "video_id": "extracted from input or generated",
    "confidence_index": 0-100, 
    "analysis_sources": ["Gemini", "ClarifAI"]
  }},
  "summary": {{
    "content_overview": "Brief overview of video content",
    "key_strengths": ["Strength 1", "Strength 2"],
    "improvement_areas": ["Area 1", "Area 2"],
    "overall_performance_score": 0-100
  }},
  "performance_metrics": {{
    "engagement": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "insights": "Explanation comparing both analyses",
      "breakdown": {{
        "hook_effectiveness": 0-100,
        "emotional_impact": 0-100,
        "audience_retention": 0-100,
        "attention_score": 0-100
      }}
    }},
    "shareability": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "insights": "Explanation comparing both analyses",
      "breakdown": {{
        "uniqueness": 0-100,
        "relevance": 0-100,
        "trending_potential": 0-100
      }}
    }},
    "conversion_potential": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "insights": "Explanation comparing both analyses",
      "breakdown": {{
        "call_to_action_clarity": 0-100,
        "value_proposition": 0-100,
        "persuasiveness": 0-100
      }}
    }},
    "viral_potential": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "detailed_analysis": "Analysis of viral qualities",
      "factors": ["Factor 1", "Factor 2", "Factor 3"],
      "breakdown": {{
        "uniqueness": 0-100,
        "shareability": 0-100,
        "emotional_impact": 0-100,
        "relevance": 0-100,
        "trending_potential": 0-100
      }}
    }}
  }},
  "representation_metrics": {{
    "overall_score": 0-100,
    "confidence": "High/Medium/Low",
    "insights": "Analysis of demographic representation quality, combining both analyses",
    "demographics_breakdown": {{
      "gender_distribution": {{
        "male": 0-100,
        "female": 0-100,
        "other/nonbinary": 0-100
      }},
      "age_distribution": {{
        "0-17": 0-100,
        "18-24": 0-100,
        "25-34": 0-100,
        "35-44": 0-100,
        "45-64": 0-100,
        "65+": 0-100
      }},
      "ethnicity_distribution": {{
        "caucasian": 0-100,
        "asian": 0-100,
        "black": 0-100,
        "hispanic": 0-100,
        "middle_eastern": 0-100,
        "other": 0-100
      }}
    }},
    "comparative_analysis": "Explanation of how the analyses differ in their demographic assessments and which is more likely correct based on confidence factors"
  }},
  "content_analysis": {{
    "style": "Description of content style",
    "tone": "Description of content tone",
    "pacing": "Analysis of editing and timing",
    "visual_quality": {{
      "score": 0-100,
      "lighting": "Description of lighting quality",
      "composition": "Description of visual composition",
      "colors": "Description of color scheme"
    }},
    "audio_quality": {{
      "score": 0-100,
      "clarity": "Description of audio clarity",
      "background_noise": "Assessment of background noise",
      "music": "Description of music if present"
    }}
  }},
  "audience_fit": {{
    "primary_audience": ["Audience Segment 1", "Audience Segment 2"],
    "audience_match_scores": {{
      "Gen Z": 0-100,
      "Millennials": 0-100,
      "Gen X": 0-100,
      "Baby Boomers": 0-100
    }},
    "platform_fit": {{
      "Instagram": 0-100,
      "TikTok": 0-100,
      "YouTube": 0-100,
      "Facebook": 0-100
    }}
  }},
  "recommendations": {{
    "priority_improvements": ["Recommendation 1", "Recommendation 2"],
    "optimization_suggestions": {{
      "content": ["Suggestion 1", "Suggestion 2"],
      "technical": ["Suggestion 1", "Suggestion 2"],
      "audience_targeting": ["Suggestion 1", "Suggestion 2"]
    }}
  }}
}}
```

For demographic data specifically, carefully compare the gender, age, and ethnicity distributions from both analyses. Where there are differences, explain why one might be more accurate than the other, and create a best estimate synthesis. Prioritize Gemini's demographic analysis but improve it with insights from ClarifAI where appropriate.

IMPORTANT: Ensure that all percentage values in demographics are numerical values (not strings), and that each distribution category (gender, age, ethnicity) has percentages that add up to approximately 100."""

    # Configure the model for more consistent output
    model.temperature = 0.2
    model.top_p = 0.8
    model.top_k = 40
    
    print("Generating unified analysis...")
    try:
        # Generate the response
        response = model.generate_content(unification_prompt)
        
        if not response.text:
            raise ValueError("No response generated from model")
            
        response_text = response.text
        
        # Extract JSON from the response
        json_pattern = r'\{[\s\S]*\}'
        json_match = re.search(json_pattern, response_text)
        
        if not json_match:
            raise ValueError("No JSON found in response")
            
        json_str = json_match.group()
        
        # Try to parse the JSON
        try:
            unified_analysis = json.loads(json_str)
            print("Successfully parsed unified analysis JSON")
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print("Attempting to fix common JSON issues...")
            # Try to fix common JSON issues
            json_str = json_str.replace('\n', ' ').replace('\r', '')
            # Remove trailing commas in objects and arrays
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            
            try:
                unified_analysis = json.loads(json_str)
                print("Successfully parsed fixed JSON")
            except json.JSONDecodeError:
                print("Could not fix JSON, using fallback merge")
                return fallback_merge(gemini_analysis, clarifai_analysis)
        
        # Add a validation step
        validated_analysis = validate_unified_analysis(unified_analysis, gemini_analysis, clarifai_analysis)
        
        return validated_analysis
    except Exception as e:
        print(f"Error generating unified analysis: {e}")
        # Fallback to a simpler merge if the sophisticated approach fails
        return fallback_merge(gemini_analysis, clarifai_analysis)

def validate_unified_analysis(unified_analysis: Dict[str, Any], 
                             gemini_analysis: Dict[str, Any], 
                             clarifai_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the unified analysis with a second LLM pass to ensure quality and completeness.
    """
    try:
        # First, let's check for and fix any non-numeric demographic data
        unified_analysis = validate_demographic_data_in_unified(unified_analysis)
        
        # Then, ensure the required structure exists for frontend compatibility
        unified_analysis = ensure_frontend_compatible_analysis(unified_analysis)
        
        # Then, let's verify the JSON structure of the unified_analysis
        # Convert to string and back to ensure it's valid JSON
        unified_json_str = json.dumps(unified_analysis)
        unified_analysis = json.loads(unified_json_str)
        
        validation_prompt = f"""
You are an expert AI validator checking a unified video analysis for quality, completeness, and accuracy.

Review the unified analysis below and validate that it:
1. Properly synthesizes insights from both source analyses
2. Addresses and reconciles contradictions appropriately
3. Provides appropriate confidence ratings where metrics differ
4. Contains complete and well-structured data in all required fields
5. Offers genuinely actionable recommendations

If you find any issues, you should fix them directly in the JSON.

Unified Analysis to Validate:
```json
{json.dumps(unified_analysis)}
```

Response Instructions:
- Return ONLY the valid JSON with no additional text
- Preserve the existing structure exactly
- Improve any sections that lack depth or detail
- Ensure all metrics have appropriate confidence ratings
- Fix any logical inconsistencies or missing pieces
"""

        # Use a slightly different temperature for the validation pass
        model.temperature = 0.1
        
        print("Validating unified analysis...")
        
        # Generate the validation response
        response = model.generate_content(validation_prompt)
        
        if not response.text:
            print("Validation produced no response, returning original unified analysis")
            return unified_analysis
            
        response_text = response.text
        
        # Extract JSON from the response
        json_pattern = r'\{[\s\S]*\}'
        json_match = re.search(json_pattern, response_text)
        
        if not json_match:
            print("Validation produced no valid JSON, returning original unified analysis")
            return unified_analysis
            
        json_str = json_match.group()
        
        # Validate the JSON before returning
        try:
            validated_analysis = json.loads(json_str)
            # Ensure the validated analysis still has the required structure
            validated_analysis = ensure_frontend_compatible_analysis(validated_analysis)
            print("Validation successful, returning validated analysis")
            return validated_analysis
        except json.JSONDecodeError as e:
            print(f"Validation produced invalid JSON: {e}, returning original unified analysis")
            return unified_analysis
        
    except Exception as e:
        print(f"Error in validation: {e}")
        # If validation fails, return the original unified analysis
        return unified_analysis

def validate_demographic_data_in_unified(unified_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix demographic data in unified analysis to ensure all values are numerical.
    This function is similar to validate_demographic_data in structured_analysis.py but adapted
    for the unified analysis structure.
    
    Args:
        unified_analysis: The unified analysis data
        
    Returns:
        Dict with validated/fixed demographic data
    """
    print("Validating demographic data in unified analysis...")
    
    # Handle different structures that might contain demographic data
    if "representation_metrics" in unified_analysis and "demographics_breakdown" in unified_analysis["representation_metrics"]:
        demographics = unified_analysis["representation_metrics"]["demographics_breakdown"]
        distributions = ["age_distribution", "gender_distribution", "ethnicity_distribution"]
    elif "clarifai_analysis" in unified_analysis and "demographics" in unified_analysis["clarifai_analysis"]:
        demographics = unified_analysis["clarifai_analysis"]["demographics"]
        distributions = ["age_distribution", "gender_distribution", "ethnicity_distribution"]
    elif "demographics" in unified_analysis:
        demographics = unified_analysis["demographics"]
        distributions = ["age_distribution", "gender_distribution", "ethnicity_distribution"]
    elif "gemini_analysis" in unified_analysis and "Demographic Analysis" in unified_analysis["gemini_analysis"]:
        demographics = unified_analysis["gemini_analysis"]["Demographic Analysis"]
        # Map Gemini's keys to our standard keys
        distributions = []
        key_mapping = {
            "Gender Distribution": "gender_distribution",
            "Age Distribution": "age_distribution", 
            "Ethnicity Distribution": "ethnicity_distribution"
        }
        # Create a new standardized structure
        standardized_demographics = {}
        for gemini_key, standard_key in key_mapping.items():
            if gemini_key in demographics:
                standardized_demographics[standard_key] = demographics[gemini_key]
                distributions.append(standard_key)
        
        # Replace with standardized structure
        demographics = standardized_demographics
    else:
        print("No demographics data found to validate in unified analysis")
        return unified_analysis
    
    text_value_mappings = {
        "high": 80.0,
        "majority": 75.0,
        "predominant": 85.0,
        "strong": 70.0,
        "substantially": 65.0,
        "substantial": 65.0,
        "notable": 50.0,
        "medium": 50.0,
        "moderate": 40.0,
        "some": 30.0,
        "present": 25.0,
        "low": 20.0,
        "minimal": 10.0,
        "trace": 5.0,
        "strongly skewed towards": 90.0
    }
    
    for dist_key in distributions:
        if dist_key in demographics:
            distribution = demographics[dist_key]
            
            # Skip if already empty
            if not distribution:
                continue
                
            fixed_distribution = {}
            for demo_key, value in distribution.items():
                # If value is a string but not a number string, convert it
                if isinstance(value, str):
                    if value.replace('.', '', 1).isdigit():
                        # It's a numeric string, convert to float
                        fixed_distribution[demo_key] = float(value)
                    else:
                        # It's a text value, map it to a number
                        lowercase_value = value.lower().strip()
                        if lowercase_value in text_value_mappings:
                            fixed_distribution[demo_key] = text_value_mappings[lowercase_value]
                        else:
                            # Default value if no mapping found
                            print(f"Warning: Converting unmapped text value '{value}' to default value 50.0")
                            fixed_distribution[demo_key] = 50.0
                else:
                    # Already a number, keep as is
                    fixed_distribution[demo_key] = float(value) if isinstance(value, (int, float)) else 50.0
            
            # Replace with fixed distribution
            demographics[dist_key] = fixed_distribution
    
    # Update the unified_analysis with fixed demographics data
    if "representation_metrics" in unified_analysis and "demographics_breakdown" in unified_analysis["representation_metrics"]:
        unified_analysis["representation_metrics"]["demographics_breakdown"] = demographics
    elif "clarifai_analysis" in unified_analysis and "demographics" in unified_analysis["clarifai_analysis"]:
        unified_analysis["clarifai_analysis"]["demographics"] = demographics
    elif "demographics" in unified_analysis:
        unified_analysis["demographics"] = demographics
    elif "gemini_analysis" in unified_analysis and "Demographic Analysis" in unified_analysis["gemini_analysis"]:
        # Convert back to Gemini's structure
        gemini_demographics = {}
        key_mapping = {
            "gender_distribution": "Gender Distribution",
            "age_distribution": "Age Distribution", 
            "ethnicity_distribution": "Ethnicity Distribution"
        }
        for standard_key, gemini_key in key_mapping.items():
            if standard_key in demographics:
                gemini_demographics[gemini_key] = demographics[standard_key]
        
        # Replace Gemini's demographics with validated version
        unified_analysis["gemini_analysis"]["Demographic Analysis"] = gemini_demographics
    
    print("Demographics data in unified analysis validated and fixed if needed")
    return unified_analysis

def ensure_frontend_compatible_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the analysis has the required structure for frontend compatibility.
    
    Args:
        analysis: The analysis data to validate
        
    Returns:
        Dict with the required structure for frontend compatibility
    """
    # Make sure metadata exists
    if "metadata" not in analysis:
        analysis["metadata"] = {
            "timestamp": datetime.now().isoformat(),
            "video_id": "unknown",
            "confidence_index": 70,
            "analysis_sources": ["Gemini", "ClarifAI"]
        }
        
    # Make sure summary exists
    if "summary" not in analysis:
        analysis["summary"] = {
            "content_overview": "Content overview not available",
            "key_strengths": [],
            "improvement_areas": [],
            "overall_performance_score": 50
        }
        
    # Make sure performance_metrics exists with all required metrics
    if "performance_metrics" not in analysis:
        analysis["performance_metrics"] = {}
        
    # Check individual metrics
    metrics = ["engagement", "shareability", "conversion_potential", "viral_potential"]
    for metric in metrics:
        if metric not in analysis["performance_metrics"]:
            analysis["performance_metrics"][metric] = {
                "score": 50,
                "confidence": "Medium",
                "insights": f"No {metric} data available",
                "breakdown": {}
            }
        
        # Make sure breakdown exists for each metric
        if "breakdown" not in analysis["performance_metrics"][metric]:
            analysis["performance_metrics"][metric]["breakdown"] = {}
            
        # Set default breakdown fields if empty
        if len(analysis["performance_metrics"][metric]["breakdown"]) == 0:
            if metric == "engagement":
                analysis["performance_metrics"][metric]["breakdown"] = {
                    "hook_effectiveness": 50,
                    "emotional_impact": 50,
                    "audience_retention": 50,
                    "attention_score": 50
                }
            elif metric == "shareability":
                analysis["performance_metrics"][metric]["breakdown"] = {
                    "uniqueness": 50,
                    "relevance": 50,
                    "trending_potential": 50
                }
            elif metric == "conversion_potential":
                analysis["performance_metrics"][metric]["breakdown"] = {
                    "call_to_action_clarity": 50,
                    "value_proposition": 50,
                    "persuasiveness": 50
                }
            elif metric == "viral_potential":
                analysis["performance_metrics"][metric]["breakdown"] = {
                    "uniqueness": 50,
                    "shareability": 50,
                    "emotional_impact": 50,
                    "relevance": 50, 
                    "trending_potential": 50
                }
    
    # Make sure representation_metrics exists with demographics_breakdown
    if "representation_metrics" not in analysis:
        analysis["representation_metrics"] = {
            "overall_score": 50,
            "confidence": "Medium",
            "insights": "No representation data available",
            "demographics_breakdown": {
                "gender_distribution": {},
                "age_distribution": {},
                "ethnicity_distribution": {}
            }
        }
    elif "demographics_breakdown" not in analysis["representation_metrics"]:
        analysis["representation_metrics"]["demographics_breakdown"] = {
            "gender_distribution": {},
            "age_distribution": {},
            "ethnicity_distribution": {}
        }
        
    # Make sure primary_audience exists with platform_fit
    if "primary_audience" not in analysis:
        analysis["primary_audience"] = {
            "demographic": "General audience",
            "confidence": "Medium",
            "platform_fit": {
                "Instagram": 50,
                "TikTok": 50,
                "YouTube": 50,
                "Facebook": 50
            }
        }
    elif "platform_fit" not in analysis["primary_audience"]:
        analysis["primary_audience"]["platform_fit"] = {
            "Instagram": 50,
            "TikTok": 50,
            "YouTube": 50,
            "Facebook": 50
        }
        
    # Convert platform_suitability to platform_fit if it exists
    if "audience_fit" in analysis:
        if "platform_suitability" in analysis["audience_fit"] and "platform_fit" not in analysis["audience_fit"]:
            analysis["audience_fit"]["platform_fit"] = analysis["audience_fit"]["platform_suitability"]
            
        # Ensure primary_audience exists if audience_fit exists
        if "primary_audience" not in analysis["audience_fit"]:
            analysis["audience_fit"]["primary_audience"] = "General audience"
            
        # Make sure platform_fit exists in audience_fit
        if "platform_fit" not in analysis["audience_fit"]:
            analysis["audience_fit"]["platform_fit"] = {
                "Instagram": 50,
                "TikTok": 50,
                "YouTube": 50,
                "Facebook": 50
            }
            
    # Make sure secondary_audiences exists
    if "secondary_audiences" not in analysis:
        analysis["secondary_audiences"] = []
        
    return analysis

def fallback_merge(gemini_analysis: Dict[str, Any], clarifai_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple fallback merging of analyses if the sophisticated approach fails.
    """
    print("Using fallback merge approach...")
    
    # Extract platform suitability data if available
    platform_fit = {}
    if "audience_fit" in clarifai_analysis and "platform_fit" in clarifai_analysis["audience_fit"]:
        platform_fit = clarifai_analysis["audience_fit"]["platform_fit"]
    elif "platform_fit" in clarifai_analysis:
        platform_fit = clarifai_analysis["platform_fit"]
    # Check for platform_suitability as a fallback
    elif "audience_fit" in clarifai_analysis and "platform_suitability" in clarifai_analysis["audience_fit"]:
        platform_fit = clarifai_analysis["audience_fit"]["platform_suitability"]
    elif "platform_suitability" in clarifai_analysis:
        platform_fit = clarifai_analysis["platform_suitability"]
    else:
        # Default platform fit data if nothing found
        platform_fit = {
            "Instagram": 50,
            "TikTok": 50,
            "YouTube": 50,
            "Facebook": 50
        }
    
    # Ensure we have demographic data
    demographics_breakdown = {}
    if "demographics" in clarifai_analysis:
        demographics_breakdown = {
            "gender_distribution": clarifai_analysis["demographics"].get("gender_distribution", {}),
            "age_distribution": clarifai_analysis["demographics"].get("age_distribution", {}),
            "ethnicity_distribution": clarifai_analysis["demographics"].get("ethnicity_distribution", {})
        }
    
    # Get performance metrics if available
    perf_metrics = {}
    if "performance_metrics" in clarifai_analysis:
        perf_metrics = clarifai_analysis["performance_metrics"]
    
    # Create a basic merged structure that matches what the frontend expects
    merged = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "video_id": gemini_analysis.get("id", "unknown"),
            "confidence_index": 70,
            "analysis_sources": ["Gemini", "ClarifAI"]
        },
        "summary": {
            "content_overview": clarifai_analysis.get("overview", {}).get("content_summary", "Content summary not available"),
            "key_strengths": gemini_analysis.get("analysis", {}).get("Performance Metrics", {}).get("Key Strengths", []),
            "improvement_areas": gemini_analysis.get("analysis", {}).get("Performance Metrics", {}).get("Improvement Suggestions", []),
            "overall_performance_score": perf_metrics.get("engagement_score", 50)
        },
        "performance_metrics": {
            "engagement": {
                "score": perf_metrics.get("engagement_score", 50),
                "confidence": "Medium",
                "insights": "Combined analysis of engagement factors",
                "breakdown": {
                    "hook_effectiveness": perf_metrics.get("hook_score", 50),
                    "emotional_impact": perf_metrics.get("emotional_impact", 50),
                    "audience_retention": perf_metrics.get("retention_score", 50),
                    "attention_score": int(gemini_analysis.get("analysis", {}).get("Performance Metrics", {}).get("Attention Score", 50))
                }
            },
            "shareability": {
                "score": perf_metrics.get("shareability", 50),
                "confidence": "Medium",
                "insights": "Analysis of content's potential to be shared",
                "breakdown": {
                    "uniqueness": 50,
                    "relevance": 50,
                    "trending_potential": 50
                }
            },
            "conversion_potential": {
                "score": perf_metrics.get("ctr_potential", 50),
                "confidence": "Medium",
                "insights": "Analysis of conversion potential based on content",
                "breakdown": {
                    "call_to_action_clarity": 50,
                    "value_proposition": 50,
                    "persuasiveness": 50
                }
            },
            "viral_potential": {
                "score": 50,
                "confidence": "Medium",
                "detailed_analysis": "Analysis of the content's viral qualities",
                "factors": ["Relatability", "Emotional impact", "Uniqueness"],
                "breakdown": {
                    "uniqueness": 50,
                    "shareability": perf_metrics.get("shareability", 50),
                    "emotional_impact": 50,
                    "relevance": 50,
                    "trending_potential": 50
                }
            }
        },
        "representation_metrics": {
            "overall_score": perf_metrics.get("representation_index", 50),
            "confidence": "Medium",
            "insights": "Analysis of demographic representation",
            "demographics_breakdown": demographics_breakdown,
            "diversity_score": 50,
            "inclusion_rating": 50,
            "appeal_breadth": 50
        },
        "primary_audience": {
            "demographic": clarifai_analysis.get("audience_fit", {}).get("primary_audience", "General audience"),
            "confidence": "Medium",
            "platform_fit": platform_fit
        },
        "secondary_audiences": [
            {
                "demographic": audience,
                "confidence": "Medium",
                "reasons": ["Audience interest match", "Content relevance"]
            } for audience in clarifai_analysis.get("audience_fit", {}).get("secondary_audiences", [])
        ],
        "gemini_analysis": gemini_analysis.get("analysis", {}),
        "clarifai_analysis": clarifai_analysis
    }
    
    return merged

def upload_json_to_s3(data: Dict[str, Any], bucket: str, s3_object_name: str):
    """Uploads a dictionary as a JSON file to S3."""
    try:
        json_string = json.dumps(data, indent=2, ensure_ascii=False)
        # Encode the string to bytes
        json_bytes = json_string.encode('utf-8')

        print(f"Uploading JSON data to s3://{bucket}/{s3_object_name}")
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_object_name,
            Body=json_bytes,
            ContentType='application/json',
            ACL='private' # Keep analysis results private by default
        )
        print(f"Successfully uploaded JSON to s3://{bucket}/{s3_object_name}")
    except Exception as e:
        print(f"Error uploading JSON to S3: {str(e)}")
        # Don't raise, allow local saving to proceed if possible

def save_unified_analysis(unified_analysis: Dict[str, Any]) -> str:
    """Save the unified analysis locally and upload to S3."""
    filename = None
    analysis_id = unified_analysis.get("metadata", {}).get("id")

    try:
        # Verify JSON validity before saving/uploading
        json_str = json.dumps(unified_analysis, indent=2, ensure_ascii=False)
        verified_analysis = json.loads(json_str)

        # --- Save Locally (optional, good for debugging) ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Use analysis_id if available for local filename, otherwise timestamp
        local_filename_part = analysis_id if analysis_id else f"ts_{timestamp}"
        local_filename = f"unified_analyses/unified_analysis_{local_filename_part}.json"
        try:
            with open(local_filename, 'w', encoding='utf-8') as f:
                f.write(json_str) # Write the verified string
            print(f"Unified analysis saved locally to: {local_filename}")
        except Exception as e:
            print(f"Error saving analysis locally: {e}")
        # ---------------------------------------------------

        # --- Upload to S3 --- A
        if analysis_id and S3_BUCKET_NAME:
            s3_object_key = f"analysis-results/{analysis_id}.json"
            upload_json_to_s3(verified_analysis, S3_BUCKET_NAME, s3_object_key)
        else:
            print("Skipping S3 upload: Analysis ID or S3 Bucket Name missing.")
        # -------------------

        return local_filename # Return local filename for consistency if needed

    except json.JSONDecodeError as e:
        print(f"Error in JSON structure when saving unified analysis: {e}")
        # Save simplified error version locally
        simplified = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "error": f"JSON validation error: {str(e)}",
                "partial_data": True,
                "id": analysis_id
            },
            "raw_data": str(unified_analysis)[:1000] + "..." if len(str(unified_analysis)) > 1000 else str(unified_analysis)
        }
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        local_filename_part = analysis_id if analysis_id else f"error_ts_{timestamp}"
        filename = f"unified_analyses/unified_analysis_{local_filename_part}_error.json"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(simplified, f, indent=2)
            print(f"Error occurred. Simplified analysis saved locally to: {filename}")
        except Exception as e_save:
             print(f"Could not save error analysis locally: {e_save}")
        # Attempt to upload error report to S3 as well
        if analysis_id and S3_BUCKET_NAME:
            s3_error_key = f"analysis-results/{analysis_id}_error.json"
            try:
                 upload_json_to_s3(simplified, S3_BUCKET_NAME, s3_error_key)
                 print(f"Uploaded simplified error analysis to S3: {s3_error_key}")
            except Exception as e_s3_save:
                 print(f"Could not upload error analysis to S3: {e_s3_save}")
        return filename

    except Exception as e:
        print(f"General error saving unified analysis: {e}")
        # Log the error but don't necessarily stop the entire analysis process
        # Depending on where this is called, you might want to raise e
        return None # Indicate saving failed

def analyze_video(video_url_or_path: str, analysis_id: str, analysis_name: str, progress_callback=None) -> Dict[str, Any]:
    """
    Main function to analyze a video URL or path and generate a unified analysis.

    Args:
        video_url_or_path: URL of the video or path to a local video file
        analysis_id: The unique ID generated for this analysis session
        analysis_name: User-provided name for the analysis
        progress_callback: Optional callback function to report progress
            Function signature: progress_callback(stage: str, progress_pct: float)

    Returns:
        Unified analysis combining insights from both Gemini and ClarifAI
    """
    try:
        is_url = video_url_or_path.startswith(('http://', 'https://', 's3://'))
        source_type = "URL" if is_url else "file"
        print(f"Starting unified analysis for video {source_type}: {video_url_or_path} (Name: {analysis_name}, ID: {analysis_id})")
        
        # Notify start of gemini and clarifai analysis
        if progress_callback:
            progress_callback("gemini_started", 0)
            progress_callback("clarifai_started", 0)
            
        # Run both analyses in parallel
        gemini_analysis, clarifai_analysis = run_analyses_in_parallel(video_url_or_path, progress_callback)
        
        # Check if both analyses have errors
        gemini_has_error = "error" in gemini_analysis
        clarifai_has_error = "error" in clarifai_analysis.get("metadata", {})
        
        # Notify completion of individual analyses
        if not gemini_has_error and progress_callback:
            progress_callback("gemini_complete", 40)
            
        if not clarifai_has_error and progress_callback:
            progress_callback("clarifai_complete", 60)
        
        if gemini_has_error and clarifai_has_error:
            print("WARNING: Both analyses had errors. The unified analysis may be limited.")
        elif gemini_has_error:
            print("WARNING: Gemini analysis had errors. Some insights may be limited.")
        elif clarifai_has_error:
            print("WARNING: ClarifAI analysis had errors. Some insights may be limited.")
        
        # Notify start of unified analysis generation
        if progress_callback:
            progress_callback("generating_unified", 70)
            
        # Combine the analyses
        unified_analysis = combine_analyses(gemini_analysis, clarifai_analysis)
        
        # Validate demographic data before full validation
        unified_analysis = validate_demographic_data_in_unified(unified_analysis)
        
        # Notify start of validation
        if progress_callback:
            progress_callback("validating_unified", 80)
            
        # Add analysis ID, name, and error information to metadata BEFORE saving
        if "metadata" not in unified_analysis:
            unified_analysis["metadata"] = {}
        unified_analysis["metadata"]["id"] = analysis_id
        unified_analysis["metadata"]["analysis_name"] = analysis_name
        
        if gemini_has_error or clarifai_has_error:
            unified_analysis["metadata"]["has_errors"] = True
            unified_analysis["metadata"]["error_details"] = {
                "gemini_error": gemini_analysis.get("error") if gemini_has_error else None,
                "clarifai_error": clarifai_analysis.get("metadata", {}).get("error") if clarifai_has_error else None
            }
        
        # Ensure the analysis is frontend compatible
        unified_analysis = ensure_frontend_compatible_analysis(unified_analysis)
        
        # Save the unified analysis (which now includes the ID and name)
        save_unified_analysis(unified_analysis)
        
        return unified_analysis
        
    except Exception as e:
        print(f"Error in unified analysis (ID: {analysis_id}, Name: {analysis_name}): {e}")
        # Create a basic error analysis that can be returned
        error_analysis = {
            "metadata": {
                "id": analysis_id,
                "analysis_name": analysis_name,
                "timestamp": datetime.now().isoformat(),
                "video_id": "error_" + os.path.basename(video_url_or_path).split('?')[0],
                "has_errors": True,
                "error_details": {
                    "main_error": str(e)
                }
            },
            "summary": {
                "content_overview": "Analysis failed due to an error",
                "key_strengths": [],
                "improvement_areas": ["Try again with a different video"],
                "overall_performance_score": 0
            },
            "error": str(e)
        }
        
        # Ensure error analysis is frontend compatible
        error_analysis = ensure_frontend_compatible_analysis(error_analysis)
        
        # Try to save even the error analysis
        try:
            save_unified_analysis(error_analysis)
        except:
            print(f"Could not save error analysis for ID: {analysis_id}")
            
        return error_analysis

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Test unified video analysis with URL or local file')
    parser.add_argument('--url', type=str, help='URL of the video to analyze')
    parser.add_argument('--file', type=str, help='Path to local video file to analyze')
    
    args = parser.parse_args()
    
    if args.url:
        # Test with URL
        print(f"Starting unified analysis test with video URL: {args.url}")
        result = analyze_video(args.url, "test_url_analysis", "Test URL Analysis")
        print("Analysis completed")
        
        # Save result to file for inspection
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"unified_url_analysis_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"Analysis saved to: {output_file}")
        
    elif args.file:
        # Test with local file
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
            
        print(f"Starting unified analysis test with local file: {args.file}")
        result = analyze_video(args.file, "test_file_analysis", "Test File Analysis")
        print("Analysis completed")
        
        # Save result to file for inspection
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"unified_file_analysis_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"Analysis saved to: {output_file}")
        
    else:
        # Default test with a sample YouTube video
        video_url = "https://www.youtube.com/shorts/Ed8tZ-Ny36I"
        print("No URL or file specified. Using default test URL.")
        print(f"Starting unified analysis test with video: {video_url}")
        result = analyze_video(video_url, "test_default_analysis", "Test Default Analysis")
        print("Analysis completed")
        
        # Save result to file for inspection
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = f"unified_analysis_{timestamp}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        print(f"Analysis saved to: {output_file}") 
