"""
Utility functions for ensuring frontend compatibility with analysis outputs.
"""

import os
import json
from typing import Dict, Any
from datetime import datetime

def ensure_frontend_compatible_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures the analysis data structure is compatible with the frontend requirements.
    
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
                "gender_distribution": {
                    "male": 50,
                    "female": 50
                },
                "age_distribution": {},
                "ethnicity_distribution": {}
            },
            "diversity_score": 50,
            "inclusion_rating": 50,
            "appeal_breadth": 50
        }
    elif "demographics_breakdown" not in analysis["representation_metrics"]:
        analysis["representation_metrics"]["demographics_breakdown"] = {
            "gender_distribution": {
                "male": 50,
                "female": 50
            },
            "age_distribution": {},
            "ethnicity_distribution": {}
        }
    else:
        # Filter gender distribution to only include male and female
        gender_dist = analysis["representation_metrics"]["demographics_breakdown"].get("gender_distribution", {})
        if gender_dist:
            # Extract male and female values
            male_value = gender_dist.get("male", 0)
            female_value = gender_dist.get("female", 0)
            
            # If there's a third category like "other" or "nonbinary", redistribute its value
            other_keys = [k for k in gender_dist.keys() if k.lower() not in ["male", "female"]]
            other_total = sum(gender_dist.get(k, 0) for k in other_keys)
            
            if other_total > 0:
                # Proportionally distribute the "other" values to male and female
                if male_value + female_value > 0:
                    male_ratio = male_value / (male_value + female_value)
                    female_ratio = female_value / (male_value + female_value)
                    
                    male_value += other_total * male_ratio
                    female_value += other_total * female_ratio
                else:
                    # If both are 0, split evenly
                    male_value = other_total / 2
                    female_value = other_total / 2
            
            # Replace with filtered distribution
            analysis["representation_metrics"]["demographics_breakdown"]["gender_distribution"] = {
                "male": male_value,
                "female": female_value
            }
        
    # Make sure audience_analysis exists and contains primary_audience
    if "audience_analysis" not in analysis:
        # See if we can build it from audience_fit or primary_audience
        if "audience_fit" in analysis:
            analysis["audience_analysis"] = {
                "primary_audience": {
                    "demographic": analysis["audience_fit"].get("primary_audience", "General audience"),
                    "confidence": "Medium",
                    "platform_fit": analysis["audience_fit"].get("platform_fit", {})
                },
                "secondary_audiences": [],
                "representation_metrics": analysis.get("representation_metrics", {})
            }
            # Try to populate secondary_audiences from audience_fit
            secondary = analysis["audience_fit"].get("secondary_audiences", [])
            if secondary and isinstance(secondary, list):
                analysis["audience_analysis"]["secondary_audiences"] = [
                    {
                        "demographic": audience if isinstance(audience, str) else audience.get("demographic", "Unknown"),
                        "confidence": "Medium",
                        "reasons": ["Content relevance"]
                    } for audience in secondary
                ]
        else:
            # Create from primary_audience or default
            analysis["audience_analysis"] = {
                "primary_audience": {
                    "demographic": "General audience",
                    "confidence": "Medium",
                    "platform_fit": {
                        "instagram": 50,
                        "tiktok": 50,
                        "youtube": 50,
                        "facebook": 50
                    }
                },
                "secondary_audiences": [],
                "representation_metrics": analysis.get("representation_metrics", {})
            }
            # If there's a primary_audience, use that data instead
            if "primary_audience" in analysis:
                analysis["audience_analysis"]["primary_audience"] = {
                    "demographic": analysis["primary_audience"].get("demographic", "General audience"),
                    "confidence": analysis["primary_audience"].get("confidence", "Medium"),
                    "platform_fit": analysis["primary_audience"].get("platform_fit", {})
                }
            # If there are secondary_audiences, use those
            if "secondary_audiences" in analysis and isinstance(analysis["secondary_audiences"], list):
                analysis["audience_analysis"]["secondary_audiences"] = [
                    {
                        "demographic": audience.get("demographic", "Unknown"),
                        "confidence": audience.get("confidence", "Medium"),
                        "reasons": audience.get("reasons", ["Content relevance"])
                    } for audience in analysis["secondary_audiences"]
                ] if all(isinstance(item, dict) for item in analysis["secondary_audiences"]) else [
                    {
                        "demographic": str(audience),
                        "confidence": "Medium",
                        "reasons": ["Content relevance"]
                    } for audience in analysis["secondary_audiences"]
                ]
    # If audience_analysis already exists, make sure its representation_metrics has correct gender distribution
    elif "representation_metrics" in analysis["audience_analysis"] and "demographics_breakdown" in analysis["audience_analysis"]["representation_metrics"]:
        gender_dist = analysis["audience_analysis"]["representation_metrics"]["demographics_breakdown"].get("gender_distribution", {})
        if gender_dist:
            # Extract male and female values
            male_value = gender_dist.get("male", 0)
            female_value = gender_dist.get("female", 0)
            
            # If there's a third category like "other" or "nonbinary", redistribute its value
            other_keys = [k for k in gender_dist.keys() if k.lower() not in ["male", "female"]]
            other_total = sum(gender_dist.get(k, 0) for k in other_keys)
            
            if other_total > 0:
                # Proportionally distribute the "other" values to male and female
                if male_value + female_value > 0:
                    male_ratio = male_value / (male_value + female_value)
                    female_ratio = female_value / (male_value + female_value)
                    
                    male_value += other_total * male_ratio
                    female_value += other_total * female_ratio
                else:
                    # If both are 0, split evenly
                    male_value = other_total / 2
                    female_value = other_total / 2
            
            # Replace with filtered distribution
            analysis["audience_analysis"]["representation_metrics"]["demographics_breakdown"]["gender_distribution"] = {
                "male": male_value,
                "female": female_value
            }
    
    # Add or populate content_quality section
    if "content_quality" not in analysis:
        # Try to build it from content_analysis if available
        if "content_analysis" in analysis:
            content = analysis["content_analysis"]
            analysis["content_quality"] = {
                "visual_elements": {
                    "score": content.get("visual_quality", {}).get("score", 50),
                    "confidence": "Medium",
                    "strengths": ["Professional visuals"],
                    "improvement_areas": [],
                    "color_scheme": {
                        "dominant_colors": ["#CCCCCC", "#888888"],
                        "color_mood": content.get("visual_quality", {}).get("colors", "Neutral"),
                        "saturation_level": 50,
                        "contrast_rating": 50
                    }
                },
                "audio_elements": {
                    "score": content.get("audio_quality", {}).get("score", 50),
                    "confidence": "Medium",
                    "strengths": [content.get("audio_quality", {}).get("clarity", "Clear audio")],
                    "improvement_areas": []
                },
                "narrative_structure": {
                    "score": 50,
                    "confidence": "Medium",
                    "strengths": ["Clear narrative"],
                    "improvement_areas": []
                },
                "pacing_and_flow": {
                    "score": 50,
                    "confidence": "Medium",
                    "insights": content.get("pacing", "Well-paced content"),
                    "editing_pace": {
                        "average_cuts_per_second": "1 cut every 3 seconds",
                        "total_cut_count": 10,
                        "pacing_analysis": content.get("pacing", "Appropriate pacing for content type")
                    }
                },
                "product_presentation": {
                    "featured_products": [],
                    "overall_presentation_score": 50,
                    "confidence": "Medium"
                }
            }
        else:
            # Create default structure
            analysis["content_quality"] = {
                "visual_elements": {
                    "score": 50,
                    "confidence": "Medium",
                    "strengths": ["Good visuals"],
                    "improvement_areas": [],
                    "color_scheme": {
                        "dominant_colors": ["#CCCCCC", "#888888"],
                        "color_mood": "Neutral",
                        "saturation_level": 50,
                        "contrast_rating": 50
                    }
                },
                "audio_elements": {
                    "score": 50,
                    "confidence": "Medium",
                    "strengths": ["Clear audio"],
                    "improvement_areas": []
                },
                "narrative_structure": {
                    "score": 50,
                    "confidence": "Medium",
                    "strengths": ["Clear narrative"],
                    "improvement_areas": []
                },
                "pacing_and_flow": {
                    "score": 50,
                    "confidence": "Medium",
                    "insights": "Appropriate pacing for content type",
                    "editing_pace": {
                        "average_cuts_per_second": "1 cut every 3 seconds",
                        "total_cut_count": 10,
                        "pacing_analysis": "Balanced pacing that maintains viewer interest"
                    }
                },
                "product_presentation": {
                    "featured_products": [],
                    "overall_presentation_score": 50,
                    "confidence": "Medium"
                }
            }
    
    # Add or populate emotional_analysis section
    if "emotional_analysis" not in analysis:
        analysis["emotional_analysis"] = {
            "dominant_emotions": ["Neutral", "Interest"],
            "emotional_arc": "Stable emotional tone throughout content",
            "emotional_resonance_score": 50,
            "confidence": "Medium",
            "insights": "Content maintains a consistent emotional tone"
        }
    
    # Add or populate competitive_advantage section
    if "competitive_advantage" not in analysis:
        # Try to extract from recommendations if available
        strengths = []
        if "summary" in analysis and "key_strengths" in analysis["summary"]:
            strengths = analysis["summary"]["key_strengths"][:2] if len(analysis["summary"]["key_strengths"]) >= 2 else analysis["summary"]["key_strengths"] + ["Effective content delivery"]
        
        analysis["competitive_advantage"] = {
            "uniqueness_factors": strengths,
            "differentiation_score": 50,
            "market_positioning": "Standard positioning within the content category",
            "confidence": "Medium"
        }
    
    # Add or populate transcription_analysis section
    if "transcription_analysis" not in analysis:
        analysis["transcription_analysis"] = {
            "available": False,
            "subtitle_coverage": {
                "percentage": 0,
                "missing_segments": [],
                "quality_score": 0,
                "issues": []
            },
            "key_phrases": [],
            "confidence": "Low"
        }
    
    # Add or populate contradiction_analysis section
    if "contradiction_analysis" not in analysis:
        analysis["contradiction_analysis"] = []
    
    # Add or populate optimization_recommendations section
    if "optimization_recommendations" not in analysis:
        # Try to build from recommendations if available
        if "recommendations" in analysis:
            analysis["optimization_recommendations"] = {
                "priority_improvements": [
                    {
                        "area": area,
                        "recommendation": area,
                        "expected_impact": "Medium",
                        "confidence": "Medium"
                    } for area in analysis["recommendations"].get("priority_improvements", ["Content quality", "Engagement"])
                ],
                "a_b_testing_suggestions": [
                    {
                        "element": "Thumbnail",
                        "variations": ["Option 1", "Option 2"],
                        "expected_insights": "Determine which thumbnail generates higher click-through rates"
                    }
                ],
                "platform_specific_optimizations": {
                    "instagram": analysis["recommendations"].get("optimization_suggestions", {}).get("content", ["Use engaging captions"]),
                    "tiktok": analysis["recommendations"].get("optimization_suggestions", {}).get("content", ["Use trending sounds"]),
                    "youtube": analysis["recommendations"].get("optimization_suggestions", {}).get("technical", ["Optimize thumbnail"]),
                    "facebook": ["Target relevant demographics"]
                },
                "thumbnail_optimization": ["Use high contrast", "Include clear text overlay"]
            }
        else:
            # Create default structure
            analysis["optimization_recommendations"] = {
                "priority_improvements": [
                    {
                        "area": "Content quality",
                        "recommendation": "Improve production values",
                        "expected_impact": "Medium",
                        "confidence": "Medium"
                    },
                    {
                        "area": "Engagement",
                        "recommendation": "Add a clear call to action",
                        "expected_impact": "High",
                        "confidence": "Medium"
                    }
                ],
                "a_b_testing_suggestions": [
                    {
                        "element": "Thumbnail",
                        "variations": ["Close-up", "Wide shot"],
                        "expected_insights": "Determine which thumbnail generates higher click-through rates"
                    }
                ],
                "platform_specific_optimizations": {
                    "instagram": ["Use engaging captions"],
                    "tiktok": ["Use trending sounds"],
                    "youtube": ["Optimize thumbnail"],
                    "facebook": ["Target relevant demographics"]
                },
                "thumbnail_optimization": ["Use high contrast", "Include clear text overlay"]
            }
    
    # Handle audience fit data
    # For backward compatibility, check if primary_audience exists (old format) or audience_fit (new format)
    primary_audience_exists = "primary_audience" in analysis
    audience_fit_exists = "audience_fit" in analysis
    
    # If neither exists, create audience_fit
    if not primary_audience_exists and not audience_fit_exists:
        analysis["audience_fit"] = {
            "primary_audience": "General audience",
            "audience_match_scores": {},
            "platform_fit": {
                "Instagram": 50,
                "TikTok": 50,
                "YouTube": 50,
                "Facebook": 50
            }
        }
    # If primary_audience exists but audience_fit doesn't (old format), create audience_fit
    elif primary_audience_exists and not audience_fit_exists:
        platform_fit = {}
        if "platform_fit" in analysis["primary_audience"]:
            platform_fit = analysis["primary_audience"]["platform_fit"]
        elif "platform_suitability" in analysis["primary_audience"]:
            platform_fit = analysis["primary_audience"]["platform_suitability"]
        else:
            platform_fit = {
                "Instagram": 50,
                "TikTok": 50,
                "YouTube": 50,
                "Facebook": 50
            }
            
        analysis["audience_fit"] = {
            "primary_audience": analysis["primary_audience"].get("demographic", "General audience"),
            "audience_match_scores": {},
            "platform_fit": platform_fit
        }
    # If audience_fit exists, ensure it has the required structure
    elif audience_fit_exists:
        # Make sure platform_fit exists in audience_fit
        if "platform_fit" not in analysis["audience_fit"]:
            if "platform_suitability" in analysis["audience_fit"]:
                analysis["audience_fit"]["platform_fit"] = analysis["audience_fit"]["platform_suitability"]
            else:
                analysis["audience_fit"]["platform_fit"] = {
                    "Instagram": 50,
                    "TikTok": 50,
                    "YouTube": 50,
                    "Facebook": 50
                }
    
    # Make sure secondary_audiences exists and is an array
    if "secondary_audiences" not in analysis:
        analysis["secondary_audiences"] = []
    elif not isinstance(analysis["secondary_audiences"], list):
        # Convert to list if not already
        analysis["secondary_audiences"] = [analysis["secondary_audiences"]]
        
    # Ensure each secondary audience has the required format
    for i, audience in enumerate(analysis["secondary_audiences"]):
        if isinstance(audience, str):
            # Convert from string to object
            analysis["secondary_audiences"][i] = {
                "demographic": audience,
                "confidence": "Medium",
                "reasons": ["Content relevance"]
            }
        elif isinstance(audience, dict) and "reasons" not in audience:
            audience["reasons"] = ["Content relevance"]
            
    return analysis 
