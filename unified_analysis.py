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

# Import necessary modules for both analysis pipelines
from inference_layer import analyze_video_output
from structured_analysis import process_analysis
from clarif_ai_insights import analyze_video_multi_model, download_video_with_ytdlp, upload_to_s3, S3_BUCKET_NAME

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

def run_analyses_in_parallel(video_url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run both analysis pipelines in parallel and return their results.
    
    Args:
        video_url: URL of the video to analyze
        
    Returns:
        Tuple containing (gemini_analysis, clarifai_structured_analysis)
    """
    gemini_analysis = None
    clarifai_structured_analysis = None
    gemini_error = None
    clarifai_error = None
    
    # Create a function for Gemini analysis pipeline
    def run_gemini_analysis():
        try:
            print("Starting Gemini analysis pipeline...")
            from narrative_analyzer import analyze_video_with_gemini
            # Use the retry mechanism built into the function
            result = analyze_video_with_gemini(video_url, is_url_prompt=True, max_retries=3, initial_retry_delay=2)
            
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
        try:
            print("Starting ClarifAI analysis pipeline...")
            # 1. Download the video
            local_filename = "temp_video_" + os.path.basename(video_url).split('?')[0] + ".mp4"
            local_path = download_video_with_ytdlp(video_url, output_path=local_filename)
            
            # 2. Upload to S3
            s3_video_url = upload_to_s3(local_path, S3_BUCKET_NAME, s3_object_name=f"videos/{local_filename}")
            
            # 3. Analyze using ClarifAI models
            clarifai_result = analyze_video_multi_model(s3_video_url, sample_ms=125)
            
            # 4. Generate initial analysis
            initial_analysis = analyze_video_output(clarifai_result)
            
            # 5. Generate structured analysis
            structured_result = process_analysis(initial_analysis)
            
            # 6. Clean up local file
            if os.path.exists(local_path):
                os.remove(local_path)
                
            print("ClarifAI analysis pipeline completed successfully")
            return structured_result
        except Exception as e:
            print(f"Error in ClarifAI analysis pipeline: {e}")
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
            "video_url": video_url
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

1. Standard Analysis (Gemini): Focuses on content, style, performance metrics, visual analysis, product analysis, viral potential, and detailed observations.
2. Structured Analysis (ClarifAI): Focuses on demographic representation, emotional tone, visual elements, and audience fit.

# Your task:
Create a unified, comprehensive analysis that combines insights from both sources while resolving any contradictions.

# Guidelines:
1. CRITICAL: Compare corresponding metrics between the two analyses and reconcile any contradictions.
2. When metrics differ significantly, add a confidence rating (Low/Medium/High) based on:
   - How much the analyses agree
   - The specificity of the observations
   - Internal consistency within each analysis
3. For contradictory insights, present both perspectives with your reconciliation.
4. Use facts from BOTH analyses to create more nuanced insights.
5. Make the unified output more detailed and useful than either input alone.
6. The output must be well-structured for display in dashboards with charts, graphs, and tables.
7. IMPORTANT: Incorporate ALL metrics and insights from both analyses without omitting any key information.

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
      "breakdown": {{
        "visuals_quality": 0-100,
        "emotional_resonance": 0-100,
        "shareability_factor": 0-100,
        "relatability": 0-100,
        "uniqueness": 0-100
      }}
    }}
  }},
  "audience_analysis": {{
    "primary_audience": {{
      "demographic": "Main demographic group",
      "confidence": "High/Medium/Low",
      "platform_fit": {{
        "instagram": 0-100,
        "tiktok": 0-100,
        "youtube": 0-100,
        "facebook": 0-100
      }}
    }},
    "secondary_audiences": [
      {{
        "demographic": "Secondary demographic group",
        "confidence": "High/Medium/Low",
        "reasons": ["Reason 1", "Reason 2"]
      }}
    ],
    "representation_metrics": {{
      "diversity_score": 0-100,
      "inclusion_rating": 0-100,
      "appeal_breadth": 0-100,
      "insights": "Analysis of demographic representation",
      "demographics_breakdown": {{
        "age_distribution": {{}},
        "gender_distribution": {{}},
        "ethnicity_distribution": {{}}
      }}
    }}
  }},
  "content_quality": {{
    "visual_elements": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "strengths": ["Strength 1", "Strength 2"],
      "improvement_areas": ["Area 1", "Area 2"],
      "color_scheme": {{
        "dominant_colors": ["Color 1", "Color 2"],
        "color_mood": "Description of mood",
        "saturation_level": 0-100,
        "contrast_rating": 0-100
      }}
    }},
    "audio_elements": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "strengths": ["Strength 1", "Strength 2"],
      "improvement_areas": ["Area 1", "Area 2"]
    }},
    "narrative_structure": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "strengths": ["Strength 1", "Strength 2"],
      "improvement_areas": ["Area 1", "Area 2"]
    }},
    "pacing_and_flow": {{
      "score": 0-100,
      "confidence": "High/Medium/Low",
      "insights": "Analysis of pacing effectiveness",
      "editing_pace": {{
        "average_cuts_per_second": "e.g. 1 cut every 2.5 seconds",
        "total_cut_count": 0,
        "pacing_analysis": "Whether the editing rhythm enhances or detracts from content"
      }}
    }},
    "product_presentation": {{
      "featured_products": [
        {{
          "name": "Product name",
          "screen_time": "Duration in seconds",
          "presentation_quality": 0-100
        }}
      ],
      "overall_presentation_score": 0-100,
      "confidence": "High/Medium/Low"
    }}
  }},
  "emotional_analysis": {{
    "dominant_emotions": ["Emotion 1", "Emotion 2"],
    "emotional_arc": "Description of emotional journey",
    "emotional_resonance_score": 0-100,
    "confidence": "High/Medium/Low",
    "insights": "Analysis comparing emotional assessments"
  }},
  "competitive_advantage": {{
    "uniqueness_factors": ["Factor 1", "Factor 2"],
    "differentiation_score": 0-100,
    "market_positioning": "Analysis of content positioning",
    "confidence": "High/Medium/Low"
  }},
  "optimization_recommendations": {{
    "priority_improvements": [
      {{
        "area": "Area for improvement",
        "recommendation": "Specific action",
        "expected_impact": "High/Medium/Low",
        "confidence": "High/Medium/Low"
      }}
    ],
    "a_b_testing_suggestions": [
      {{
        "element": "Element to test",
        "variations": ["Option 1", "Option 2"],
        "expected_insights": "What you might learn"
      }}
    ],
    "platform_specific_optimizations": {{
      "instagram": ["Tip 1", "Tip 2"],
      "tiktok": ["Tip 1", "Tip 2"],
      "youtube": ["Tip 1", "Tip 2"],
      "facebook": ["Tip 1", "Tip 2"]
    }},
    "thumbnail_optimization": ["Tip 1", "Tip 2"]
  }},
  "transcription_analysis": {{
    "available": true,
    "subtitle_coverage": {{
      "percentage": 0-100,
      "missing_segments": [
        {{"start": "timestamp", "end": "timestamp"}}
      ],
      "quality_score": 0-100,
      "issues": ["Issue 1", "Issue 2"]
    }},
    "key_phrases": ["Phrase 1", "Phrase 2"],
    "confidence": "High/Medium/Low"
  }},
  "contradiction_analysis": [
    {{
      "metric": "Name of conflicting metric",
      "gemini_assessment": "What Gemini analyzed",
      "clarifai_assessment": "What ClarifAI analyzed",
      "reconciliation": "How the conflict was resolved",
      "confidence_in_reconciliation": "High/Medium/Low"
    }}
  ]
}}
```

Your analysis must be extremely thorough, leaving out no significant information from either source analysis. Ensure your unified analysis capitalizes on the unique strengths of both original analyses:

1. From Gemini: Extract detailed performance metrics, visual analysis, product insights, and viral potential.
2. From ClarifAI: Leverage demographic data, emotional tone analysis, and representation metrics.

When both analyses provide metrics for the same aspect (like engagement potential), carefully reconcile any differences and explain your reasoning.

Approach this task with exceptional thoroughness. Ensure the unified analysis provides comprehensive, actionable insights that capitalize on the strengths of both original analyses.

CRITICAL: Double-check that your response is valid, parseable JSON.
"""

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
        # First, let's verify the JSON structure of the unified_analysis
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
            print("Validation successful, returning validated analysis")
            return validated_analysis
        except json.JSONDecodeError as e:
            print(f"Validation produced invalid JSON: {e}, returning original unified analysis")
            return unified_analysis
        
    except Exception as e:
        print(f"Error in validation: {e}")
        # If validation fails, return the original unified analysis
        return unified_analysis

def fallback_merge(gemini_analysis: Dict[str, Any], clarifai_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple fallback merging of analyses if the sophisticated approach fails.
    """
    print("Using fallback merge approach...")
    
    # Create a basic merged structure
    merged = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "video_id": gemini_analysis.get("id", "unknown"),
            "confidence_index": 70,
            "analysis_sources": ["Gemini", "ClarifAI"]
        },
        "gemini_analysis": gemini_analysis.get("analysis", {}),
        "clarifai_analysis": clarifai_analysis
    }
    
    return merged

def save_unified_analysis(unified_analysis: Dict[str, Any]) -> str:
    """Save the unified analysis to a file."""
    try:
        # Verify JSON validity before saving
        json_str = json.dumps(unified_analysis)
        verified_analysis = json.loads(json_str)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"unified_analyses/unified_analysis_{timestamp}.json"
        
        # Save the result with pretty printing
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(verified_analysis, f, indent=2, ensure_ascii=False)
            
        print(f"Unified analysis saved to: {filename}")
        return filename
        
    except json.JSONDecodeError as e:
        print(f"Error in JSON structure when saving unified analysis: {e}")
        # Create a simplified version that can be saved
        simplified = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "error": f"JSON validation error: {str(e)}",
                "partial_data": True
            },
            "raw_data": str(unified_analysis)[:1000] + "..." if len(str(unified_analysis)) > 1000 else str(unified_analysis)
        }
        
        # Save the simplified version
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"unified_analyses/unified_analysis_error_{timestamp}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(simplified, f, indent=2)
            
        print(f"Error occurred. Simplified analysis saved to: {filename}")
        return filename
    except Exception as e:
        print(f"Error saving unified analysis: {e}")
        raise

def analyze_video(video_url: str) -> Dict[str, Any]:
    """
    Main function to analyze a video URL and generate a unified analysis.
    
    Args:
        video_url: URL of the video to analyze
        
    Returns:
        Unified analysis combining insights from both Gemini and ClarifAI
    """
    try:
        print(f"Starting unified analysis for video: {video_url}")
        
        # Run both analyses in parallel
        gemini_analysis, clarifai_analysis = run_analyses_in_parallel(video_url)
        
        # Check if both analyses have errors
        gemini_has_error = "error" in gemini_analysis
        clarifai_has_error = "error" in clarifai_analysis.get("metadata", {})
        
        if gemini_has_error and clarifai_has_error:
            print("WARNING: Both analyses had errors. The unified analysis may be limited.")
        elif gemini_has_error:
            print("WARNING: Gemini analysis had errors. Some insights may be limited.")
        elif clarifai_has_error:
            print("WARNING: ClarifAI analysis had errors. Some insights may be limited.")
        
        # Combine the analyses
        unified_analysis = combine_analyses(gemini_analysis, clarifai_analysis)
        
        # Add error information if any
        if "metadata" not in unified_analysis:
            unified_analysis["metadata"] = {}
        
        if gemini_has_error or clarifai_has_error:
            unified_analysis["metadata"]["has_errors"] = True
            unified_analysis["metadata"]["error_details"] = {
                "gemini_error": gemini_analysis.get("error") if gemini_has_error else None,
                "clarifai_error": clarifai_analysis.get("metadata", {}).get("error") if clarifai_has_error else None
            }
        
        # Save the unified analysis
        save_unified_analysis(unified_analysis)
        
        return unified_analysis
        
    except Exception as e:
        print(f"Error in unified analysis: {e}")
        # Create a basic error analysis that can be returned
        error_analysis = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "video_id": "error_" + os.path.basename(video_url).split('?')[0],
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
        
        # Try to save even the error analysis
        try:
            save_unified_analysis(error_analysis)
        except:
            print("Could not save error analysis")
            
        return error_analysis

if __name__ == "__main__":
    # Example usage
    video_url = "https://www.youtube.com/shorts/Ed8tZ-Ny36I"
    try:
        print(f"Starting unified analysis test with video: {video_url}")
        result = analyze_video(video_url)
        print("\n--- Unified Analysis Complete ---")
        print("Unified analysis has been saved and is ready for frontend use")
        
        # Verify the result has the expected structure
        expected_keys = ["metadata", "summary", "performance_metrics"]
        missing_keys = [key for key in expected_keys if key not in result]
        
        if missing_keys:
            print(f"Warning: Final analysis is missing these expected sections: {missing_keys}")
        else:
            print("✓ Final analysis contains all expected top-level sections")
            
    except Exception as e:
        print(f"Error in unified analysis test: {e}")
        import traceback
        traceback.print_exc() 
