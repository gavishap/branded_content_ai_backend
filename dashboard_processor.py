from typing import Dict, Any, List
import statistics
from datetime import datetime
from metrics_converter import MetricsConverter
import json

class DashboardProcessor:
    """Processes video analysis data into dashboard-friendly format."""
    
    def __init__(self):
        self.metrics_converter = MetricsConverter()
    
    def process_analysis(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process raw analysis data into dashboard components.
        
        Args:
            analysis_data: Raw analysis data from storage
            
        Returns:
            Dict containing processed data for dashboard
        """
        try:
            # Handle raw response data if present
            if "raw_response" in analysis_data.get("analysis", {}):
                try:
                    analysis_data["analysis"] = json.loads(analysis_data["analysis"]["raw_response"])
                except json.JSONDecodeError as e:
                    print(f"Error decoding raw response for {analysis_data.get('id')}: {str(e)}")
                    return self._get_default_dashboard_data(analysis_data)
            
            # Get numerical metrics using Gemini
            try:
                numerical_metrics = self.metrics_converter.convert_to_metrics(analysis_data["analysis"])
            except Exception as e:
                print(f"Error converting metrics: {str(e)}")
                numerical_metrics = self._get_default_metrics()
            
            # Extract performance metrics with fallbacks
            metrics = analysis_data["analysis"].get("Performance Metrics", {})
            detailed = analysis_data["analysis"].get("Detailed Analysis", {}).get("In-depth Video Analysis", {})
            
            # Handle old data structure
            core_strengths = detailed.get("Core Strengths", {})
            if not core_strengths and "Core Strengths on Social Media" in detailed:
                core_strengths = {
                    "Visuals": detailed["Core Strengths on Social Media"].get("Visually Appealing", ""),
                    "Content": detailed["Core Strengths on Social Media"].get("Relatable Content", ""),
                    "Pacing": detailed["Core Strengths on Social Media"].get("Length and Pacing", ""),
                    "Value": detailed["Core Strengths on Social Media"].get("Value Proposition", ""),
                    "CTA": detailed["Core Strengths on Social Media"].get("Call to Action", "")
                }
            
            viral_potential = detailed.get("Viral Potential", {})
            if not viral_potential and "Viral Video Criteria" in detailed:
                viral_potential = {
                    "Visuals": detailed["Viral Video Criteria"].get("Intriguing Visuals", ""),
                    "Emotion": detailed["Viral Video Criteria"].get("Emotional Connection", ""),
                    "Shareability": detailed["Viral Video Criteria"].get("Shareability", ""),
                    "Relatability": detailed["Viral Video Criteria"].get("Relatability", ""),
                    "Uniqueness": detailed["Viral Video Criteria"].get("Uniqueness", "")
                }
            
            # Use default values if metrics are missing
            default_metrics = {
                "Attention Score": "70",
                "Engagement Potential": "70",
                "Watch Time Retention": "70%",
                "Key Strengths": ["No strengths provided"],
                "Improvement Suggestions": ["No suggestions provided"]
            }
            
            metrics = {**default_metrics, **metrics}
            
            return {
                "metadata": {
                    "id": analysis_data.get("id", "unknown"),
                    "video_name": analysis_data.get("video_name", "unknown"),
                    "timestamp": analysis_data.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
                    "analyzed_date": datetime.strptime(
                        analysis_data.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
                        "%Y%m%d_%H%M%S"
                    ).strftime("%B %d, %Y %H:%M")
                },
                "summary_metrics": {
                    "attention_score": {
                        "value": int(str(metrics["Attention Score"]).replace("%", "")),
                        "label": "Attention Score",
                        "color": "blue",
                        "icon": "eye",
                        "details": numerical_metrics["hook_effectiveness"]
                    },
                    "engagement": {
                        "value": int(str(metrics["Engagement Potential"]).replace("%", "")),
                        "label": "Engagement Potential",
                        "color": "green",
                        "icon": "users",
                        "details": numerical_metrics["viral_metrics"]
                    },
                    "retention": {
                        "value": int(str(metrics["Watch Time Retention"]).replace("%", "")),
                        "label": "Watch Time Retention",
                        "color": "purple",
                        "icon": "clock"
                    }
                },
                "key_insights": {
                    "strengths": metrics.get("Key Strengths", ["No strengths provided"]),
                    "improvements": metrics.get("Improvement Suggestions", ["No suggestions provided"])
                },
                "content_analysis": {
                    "hook_effectiveness": {
                        "text": detailed.get("Hook", "No hook analysis provided"),
                        "metrics": numerical_metrics["hook_effectiveness"],
                        "icon": "bolt"
                    },
                    "editing_quality": {
                        "text": detailed.get("Editing", "No editing analysis provided"),
                        "metrics": numerical_metrics["editing_quality"],
                        "icon": "cut"
                    },
                    "voice_tonality": {
                        "text": detailed.get("Tonality of Voice", detailed.get("Tonality", "No tonality analysis provided")),
                        "metrics": numerical_metrics["voice_tonality"],
                        "icon": "microphone"
                    }
                },
                "viral_potential": {
                    "overall_score": numerical_metrics["viral_metrics"]["viral_probability"],
                    "criteria": [
                        {
                            "name": "Visuals",
                            "value": numerical_metrics["viral_metrics"]["visuals"],
                            "details": viral_potential.get("Visuals", "No visual analysis provided")
                        },
                        {
                            "name": "Emotional Impact",
                            "value": numerical_metrics["viral_metrics"]["emotional_connection"],
                            "details": viral_potential.get("Emotion", "No emotional analysis provided")
                        },
                        {
                            "name": "Shareability",
                            "value": numerical_metrics["viral_metrics"]["shareability"],
                            "details": viral_potential.get("Shareability", "No shareability analysis provided")
                        },
                        {
                            "name": "Relatability",
                            "value": numerical_metrics["viral_metrics"]["relatability"],
                            "details": viral_potential.get("Relatability", "No relatability analysis provided")
                        },
                        {
                            "name": "Uniqueness",
                            "value": numerical_metrics["viral_metrics"]["uniqueness"],
                            "details": viral_potential.get("Uniqueness", "No uniqueness analysis provided")
                        }
                    ]
                },
                "social_media_insights": {
                    "metrics": numerical_metrics["social_metrics"],
                    "platform_scores": numerical_metrics["social_metrics"]["platform_fit"],
                    "details": {
                        "visual_appeal": core_strengths.get("Visuals", "No visual appeal analysis provided"),
                        "content_quality": core_strengths.get("Content", "No content quality analysis provided"),
                        "pacing": core_strengths.get("Pacing", "No pacing analysis provided"),
                        "value_prop": core_strengths.get("Value", "No value proposition analysis provided"),
                        "call_to_action": core_strengths.get("CTA", "No CTA analysis provided")
                    }
                }
            }
        except Exception as e:
            print(f"Error processing analysis: {str(e)}")
            return self._get_default_dashboard_data(analysis_data)
    
    def _get_default_dashboard_data(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Returns default dashboard data when processing fails."""
        default_metrics = self._get_default_metrics()
        
        return {
            "metadata": {
                "id": analysis_data.get("id", "unknown"),
                "video_name": analysis_data.get("video_name", "unknown"),
                "timestamp": analysis_data.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
                "analyzed_date": datetime.strptime(
                    analysis_data.get("timestamp", datetime.now().strftime("%Y%m%d_%H%M%S")),
                    "%Y%m%d_%H%M%S"
                ).strftime("%B %d, %Y %H:%M")
            },
            "summary_metrics": {
                "attention_score": {
                    "value": 70,
                    "label": "Attention Score",
                    "color": "blue",
                    "icon": "eye",
                    "details": default_metrics["hook_effectiveness"]
                },
                "engagement": {
                    "value": 70,
                    "label": "Engagement Potential",
                    "color": "green",
                    "icon": "users",
                    "details": default_metrics["viral_metrics"]
                },
                "retention": {
                    "value": 70,
                    "label": "Watch Time Retention",
                    "color": "purple",
                    "icon": "clock"
                }
            },
            "key_insights": {
                "strengths": ["No strengths provided"],
                "improvements": ["No suggestions provided"]
            },
            "content_analysis": {
                "hook_effectiveness": {
                    "text": "No hook analysis provided",
                    "metrics": default_metrics["hook_effectiveness"],
                    "icon": "bolt"
                },
                "editing_quality": {
                    "text": "No editing analysis provided",
                    "metrics": default_metrics["editing_quality"],
                    "icon": "cut"
                },
                "voice_tonality": {
                    "text": "No tonality analysis provided",
                    "metrics": default_metrics["voice_tonality"],
                    "icon": "microphone"
                }
            },
            "viral_potential": {
                "overall_score": default_metrics["viral_metrics"]["viral_probability"],
                "criteria": [
                    {
                        "name": "Visuals",
                        "value": default_metrics["viral_metrics"]["visuals"],
                        "details": "No visual analysis provided"
                    },
                    {
                        "name": "Emotional Impact",
                        "value": default_metrics["viral_metrics"]["emotional_connection"],
                        "details": "No emotional analysis provided"
                    },
                    {
                        "name": "Shareability",
                        "value": default_metrics["viral_metrics"]["shareability"],
                        "details": "No shareability analysis provided"
                    },
                    {
                        "name": "Relatability",
                        "value": default_metrics["viral_metrics"]["relatability"],
                        "details": "No relatability analysis provided"
                    },
                    {
                        "name": "Uniqueness",
                        "value": default_metrics["viral_metrics"]["uniqueness"],
                        "details": "No uniqueness analysis provided"
                    }
                ]
            },
            "social_media_insights": {
                "metrics": default_metrics["social_metrics"],
                "platform_scores": default_metrics["social_metrics"]["platform_fit"],
                "details": {
                    "visual_appeal": "No visual appeal analysis provided",
                    "content_quality": "No content quality analysis provided",
                    "pacing": "No pacing analysis provided",
                    "value_prop": "No value proposition analysis provided",
                    "call_to_action": "No CTA analysis provided"
                }
            }
        }
    
    def _get_default_metrics(self):
        """Returns default metrics when conversion fails."""
        return {
            "hook_effectiveness": {
                "overall_score": 70,
                "attention_grab": 70,
                "curiosity_gap": 70,
                "relevance": 70,
                "memorability": 70,
                "reasoning": "Default value due to processing error"
            },
            "editing_quality": {
                "overall_score": 70,
                "pacing": 70,
                "visual_coherence": 70,
                "technical_quality": 70,
                "engagement_impact": 70,
                "reasoning": "Default value due to processing error"
            },
            "voice_tonality": {
                "overall_score": 70,
                "clarity": 70,
                "energy_level": 70,
                "authenticity": 70,
                "audience_match": 70,
                "reasoning": "Default value due to processing error"
            },
            "viral_metrics": {
                "viral_probability": 70,
                "visuals": 70,
                "emotional_connection": 70,
                "shareability": 70,
                "relatability": 70,
                "uniqueness": 70,
                "reasoning": "Default value due to processing error"
            },
            "social_metrics": {
                "visual_appeal": 70,
                "content_quality": 70,
                "pacing": 70,
                "value_prop": 70,
                "cta_effectiveness": 70,
                "platform_fit": {
                    "tiktok": 70,
                    "instagram": 70,
                    "youtube_shorts": 70
                },
                "reasoning": "Default value due to processing error"
            }
        }
    
    @staticmethod
    def get_trending_metrics(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate trending metrics across multiple analyses.
        
        Args:
            analyses: List of processed analyses
            
        Returns:
            Dict containing trend data
        """
        if not analyses:
            return {}
        
        # Extract metrics over time
        attention_scores = []
        engagement_scores = []
        retention_rates = []
        timestamps = []
        platform_scores = {
            "tiktok": [],
            "instagram": [],
            "youtube_shorts": []
        }
        
        for analysis in analyses:
            metrics = analysis["summary_metrics"]
            social = analysis["social_media_insights"]["platform_scores"]
            
            attention_scores.append(metrics["attention_score"]["value"])
            engagement_scores.append(metrics["engagement"]["value"])
            retention_rates.append(metrics["retention"]["value"])
            timestamps.append(analysis["metadata"]["timestamp"])
            
            # Track platform-specific scores
            for platform in platform_scores:
                platform_scores[platform].append(social[platform])
        
        return {
            "trends": {
                "attention": {
                    "current": attention_scores[-1],
                    "change": attention_scores[-1] - attention_scores[0] if len(attention_scores) > 1 else 0,
                    "history": list(zip(timestamps, attention_scores))
                },
                "engagement": {
                    "current": engagement_scores[-1],
                    "change": engagement_scores[-1] - engagement_scores[0] if len(engagement_scores) > 1 else 0,
                    "history": list(zip(timestamps, engagement_scores))
                },
                "retention": {
                    "current": retention_rates[-1],
                    "change": retention_rates[-1] - retention_rates[0] if len(retention_rates) > 1 else 0,
                    "history": list(zip(timestamps, retention_rates))
                },
                "platforms": {
                    platform: {
                        "current": scores[-1],
                        "change": scores[-1] - scores[0] if len(scores) > 1 else 0,
                        "history": list(zip(timestamps, scores))
                    }
                    for platform, scores in platform_scores.items()
                }
            },
            "averages": {
                "attention": sum(attention_scores) / len(attention_scores),
                "engagement": sum(engagement_scores) / len(engagement_scores),
                "retention": sum(retention_rates) / len(retention_rates),
                "platforms": {
                    platform: sum(scores) / len(scores)
                    for platform, scores in platform_scores.items()
                }
            }
        } 
