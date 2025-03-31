from typing import Dict, Any, List, Union
import google.generativeai as genai
import os
from dotenv import load_dotenv
import json
import re

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

class MetricsConverter:
    """Converts natural language analysis into numerical metrics using Gemini."""
    
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        # Configure model parameters for more consistent output
        self.model.generation_config = {
            "temperature": 0.4,
            "top_p": 0.8,
            "top_k": 40,
        }
        
    def process_full_analysis(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the entire analysis data and generate all required metrics.
        
        Args:
            analysis_data: Raw analysis data from narrative_analyzer
            
        Returns:
            Dict containing all dashboard metrics
        """
        try:
            # Extract the relevant parts of the analysis
            if "analysis" in analysis_data:
                analysis = analysis_data["analysis"]
            else:
                analysis = analysis_data  # Sometimes the analysis is directly provided
                
            # Extract performance metrics and detailed analysis
            performance_metrics = analysis.get("Performance Metrics", {})
            detailed_analysis = analysis.get("Detailed Analysis", {}).get("In-depth Video Analysis", {})
            
            if not detailed_analysis:
                raise ValueError("Missing required analysis sections")
            
            # Process summary metrics
            summary_metrics = self._process_summary_metrics(performance_metrics)
            
            # Process viral potential
            viral_potential = self._process_viral_potential(detailed_analysis)
            
            # Process social media insights
            social_media_insights = self._process_social_media_insights(detailed_analysis, performance_metrics)
            
            # Process content analysis
            content_analysis = self._process_content_analysis(detailed_analysis)
            
            # Compile the result
            return {
                "metadata": {
                    "video_name": analysis_data.get("video_name", "Video Analysis"),
                    "id": analysis_data.get("id", ""),
                    "timestamp": analysis_data.get("timestamp", "")
                },
                "summary_metrics": summary_metrics,
                "viral_potential": viral_potential,
                "social_media_insights": social_media_insights,
                "content_analysis": content_analysis
            }
            
        except Exception as e:
            print(f"Error processing full analysis: {str(e)}")
            # Return a default structure
            return self._get_default_dashboard_data(analysis_data)
            
    def _process_summary_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Process summary metrics from performance metrics."""
        return {
            "attention_score": {
                "value": self._extract_numeric_value(metrics.get("Attention Score", 70)),
                "description": "Overall audience attention retention"
            },
            "engagement": {
                "value": self._extract_numeric_value(metrics.get("Engagement Potential", 70)),
                "description": "Level of audience interaction expected"
            },
            "retention": {
                "value": self._extract_numeric_value(metrics.get("Watch Time Retention", "70%")),
                "description": "Percentage of viewers likely to watch to completion"
            }
        }
        
    def _process_viral_potential(self, detailed_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Process viral potential metrics."""
        # Extract viral potential data from the analysis
        viral_potential = detailed_analysis.get("Viral Potential", {})
        
        # Check if we have the scores directly in the response
        if isinstance(viral_potential, dict) and "Scores" in viral_potential:
            scores = viral_potential["Scores"]
            reasoning = viral_potential.get("Reasoning", {})
            
            # Create the criteria list
            criteria = [
                {
                    "name": "Visuals",
                    "value": int(scores.get("Visuals", 70)),
                    "description": reasoning.get("Visuals", "Visual quality assessment")
                },
                {
                    "name": "Emotional Impact",
                    "value": int(scores.get("Emotional_Impact", 70)),
                    "description": reasoning.get("Emotional_Impact", "Emotional impact assessment")
                },
                {
                    "name": "Shareability",
                    "value": int(scores.get("Shareability", 70)),
                    "description": reasoning.get("Shareability", "Shareability assessment")
                },
                {
                    "name": "Relatability",
                    "value": int(scores.get("Relatability", 70)),
                    "description": reasoning.get("Relatability", "Relatability assessment")
                },
                {
                    "name": "Uniqueness",
                    "value": int(scores.get("Uniqueness", 70)),
                    "description": reasoning.get("Uniqueness", "Uniqueness assessment")
                }
            ]
            
            # Calculate the overall score
            overall = viral_potential.get("Overall", "")
            overall_score = sum(c["value"] for c in criteria) // len(criteria)
            
        else:
            # If scores aren't directly available, use LLM to extract them
            criteria_data = self._score_viral_potential_with_llm(detailed_analysis)
            
            # Format the criteria list
            criteria = [
                {
                    "name": "Visuals",
                    "value": criteria_data.get("visuals", 70),
                    "description": criteria_data.get("visuals_reasoning", "Visual quality assessment")
                },
                {
                    "name": "Emotional Impact",
                    "value": criteria_data.get("emotional_impact", 70),
                    "description": criteria_data.get("emotional_impact_reasoning", "Emotional impact assessment")
                },
                {
                    "name": "Shareability",
                    "value": criteria_data.get("shareability", 70),
                    "description": criteria_data.get("shareability_reasoning", "Shareability assessment")
                },
                {
                    "name": "Relatability",
                    "value": criteria_data.get("relatability", 70),
                    "description": criteria_data.get("relatability_reasoning", "Relatability assessment")
                },
                {
                    "name": "Uniqueness",
                    "value": criteria_data.get("uniqueness", 70),
                    "description": criteria_data.get("uniqueness_reasoning", "Uniqueness assessment")
                }
            ]
            
            # Calculate the overall score
            overall_score = criteria_data.get("overall_score", 70)
        
        return {
            "overall_score": overall_score,
            "criteria": criteria
        }
        
    def _score_viral_potential_with_llm(self, detailed_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to extract viral potential scores from the analysis."""
        viral_section = detailed_analysis.get("Viral Potential", {})
        
        # Prepare the viral potential description for the prompt
        if isinstance(viral_section, dict):
            viral_description = json.dumps(viral_section, indent=2)
        elif isinstance(viral_section, str):
            viral_description = viral_section
        else:
            viral_description = "No specific viral potential information available."
            
        # Create a detailed prompt for the LLM
        prompt = """
        Analyze this video's viral potential information and provide numerical scores (0-100) for key viral criteria.
        
        Here's the viral potential analysis: {viral_description}
        
        For each criterion below:
        1. Carefully analyze the text
        2. Consider both explicit mentions of quality/performance and implicit indications
        3. Apply your knowledge of viral video characteristics
        4. Assign a score from 0-100 (higher = better)
        5. Provide brief reasoning for each score
        
        Criteria to score:
        - Visuals: Quality, composition, distinctiveness, color psychology, aesthetic appeal
        - Emotional Impact: Ability to trigger emotions (joy, surprise, inspiration, etc.)
        - Shareability: Reasons viewers would share (provides value, social currency, etc.)
        - Relatability: How well it connects with audience experiences or aspirations
        - Uniqueness: How differentiated it is from similar content
        
        Also calculate an overall score that weighs all factors.
        
        Respond in this exact JSON format:
        {{
            "visuals": 75,
            "visuals_reasoning": "brief reasoning",
            "emotional_impact": 80,
            "emotional_impact_reasoning": "brief reasoning",
            "shareability": 85,
            "shareability_reasoning": "brief reasoning",
            "relatability": 70,
            "relatability_reasoning": "brief reasoning",
            "uniqueness": 65,
            "uniqueness_reasoning": "brief reasoning",
            "overall_score": 75,
            "overall_reasoning": "brief explanation of overall score"
        }}
        """.format(viral_description=viral_description)
        
        # Get the response from the model
        result = self._get_gemini_response(prompt)
        
        # If we didn't get valid results, use defaults
        if not result or not isinstance(result, dict):
            return {
                "visuals": 70,
                "visuals_reasoning": "Default score due to insufficient information",
                "emotional_impact": 70,
                "emotional_impact_reasoning": "Default score due to insufficient information",
                "shareability": 70,
                "shareability_reasoning": "Default score due to insufficient information",
                "relatability": 70,
                "relatability_reasoning": "Default score due to insufficient information",
                "uniqueness": 70,
                "uniqueness_reasoning": "Default score due to insufficient information",
                "overall_score": 70,
                "overall_reasoning": "Default overall score due to insufficient information"
            }
            
        return result
    
    def _process_social_media_insights(self, detailed_analysis: Dict[str, Any], 
                                     performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Process social media insights metrics."""
        # Extract platform recommendations
        platform_recs = detailed_analysis.get("Platform Recommendations", {})
        
        # Use LLM to evaluate platform-specific performance
        platform_data = self._score_platform_performance_with_llm(detailed_analysis, platform_recs)
        
        # Determine best performing platform
        platform_scores = platform_data.get("platform_scores", {})
        best_platform = max(platform_scores, key=platform_scores.get) if platform_scores else "instagram"
        
        # Extract improvement suggestions
        improvement_suggestions = performance_metrics.get("Improvement Suggestions", [])
        
        return {
            "platform_scores": platform_scores,
            "best_performing": best_platform,
            "recommendations": platform_data.get("recommendations", improvement_suggestions if isinstance(improvement_suggestions, list) else [])
        }
        
    def _score_platform_performance_with_llm(self, detailed_analysis: Dict[str, Any], 
                                          platform_recs: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to evaluate platform-specific performance."""
        # Format the platform recommendations for the prompt
        if isinstance(platform_recs, dict):
            platform_text = json.dumps(platform_recs, indent=2)
        else:
            platform_text = str(platform_recs)
            
        # Create a detailed prompt for the LLM
        prompt = """
        Analyze this video's platform recommendations and provide numerical scores (0-100) for performance on different platforms.
        
        Here's the platform analysis: {platform_text}
        
        Based on the information provided about the video content, evaluate how well it would perform on each platform:
        - Instagram: Consider visual appeal, mobile optimization, engagement factors
        - TikTok: Consider trend alignment, hook strength, audio usage, format
        - YouTube Shorts: Consider branding, retention, discoverability, audience match
        
        For each platform:
        1. Carefully analyze the available information
        2. Consider platform-specific success factors
        3. Assign a score from 0-100 (higher = better)
        4. Provide 1-3 specific actionable recommendations for each platform
        
        Respond in this exact JSON format:
        {{
            "platform_scores": {{
                "instagram": 75,
                "tiktok": 80,
                "youtube_shorts": 70
            }},
            "recommendations": [
                "recommendation 1",
                "recommendation 2",
                "recommendation 3"
            ],
            "reasoning": {{
                "instagram": "brief reasoning",
                "tiktok": "brief reasoning",
                "youtube_shorts": "brief reasoning"
            }}
        }}
        """.format(platform_text=platform_text)
        
        # Get the response from the model
        result = self._get_gemini_response(prompt)
        
        # If we didn't get valid results, use defaults
        if not result or not isinstance(result, dict):
            return {
                "platform_scores": {
                    "instagram": 70,
                    "tiktok": 70,
                    "youtube_shorts": 70
                },
                "recommendations": [
                    "Optimize visual composition for mobile viewing",
                    "Include clear calls-to-action",
                    "Add captions for better accessibility"
                ],
                "reasoning": {
                    "instagram": "Default score due to insufficient information",
                    "tiktok": "Default score due to insufficient information",
                    "youtube_shorts": "Default score due to insufficient information"
                }
            }
            
        return result
        
    def _process_content_analysis(self, detailed_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Process content analysis metrics."""
        # Extract key components for content analysis
        hook = detailed_analysis.get("Hook", "")
        editing = detailed_analysis.get("Editing", "")
        tonality = detailed_analysis.get("Tonality", "")
        
        # Use LLM to score each component
        hook_metrics = self._score_hook_with_llm(hook)
        editing_metrics = self._score_editing_with_llm(editing)
        tonality_metrics = self._score_voice_with_llm(tonality)
        
        return {
            "hook_effectiveness": {
                "text": hook,
                "metrics": hook_metrics
            },
            "editing_quality": {
                "text": editing,
                "metrics": editing_metrics
            },
            "voice_tonality": {
                "text": tonality,
                "metrics": tonality_metrics
            }
        }
    
    def _score_hook_with_llm(self, hook_text: str) -> Dict[str, Any]:
        """Score hook effectiveness with LLM."""
        prompt = """
        Analyze this video hook description and provide numerical scores (0-100) for:
        1. Attention Grab: How quickly it captures attention
        2. Curiosity Gap: How well it creates intrigue
        3. Relevance: How well it connects to target audience
        4. Memorability: How likely viewers remember it
        
        Hook description: "{hook_text}"
        
        For each criterion:
        1. Carefully analyze the hook description
        2. Consider both explicit quality indicators and implicit effectiveness
        3. Apply your knowledge of effective video hooks
        4. Assign a score from 0-100 (higher = better)
        
        Respond in this exact JSON format:
        {{
            "attention_grab": 85,
            "curiosity_gap": 75,
            "relevance": 80,
            "memorability": 70,
            "overall_score": 78,
            "reasoning": "brief explanation"
        }}
        """.format(hook_text=hook_text)
        
        result = self._get_gemini_response(prompt)
        
        # If we didn't get valid results, use defaults
        if not result or not isinstance(result, dict):
            return {
                "attention_grab": 70,
                "curiosity_gap": 70,
                "relevance": 70,
                "memorability": 70,
                "overall_score": 70,
                "reasoning": "Default scores due to insufficient information"
            }
            
        return result
    
    def _score_editing_with_llm(self, editing_text: str) -> Dict[str, Any]:
        """Score editing quality with LLM."""
        prompt = """
        Analyze this video editing description and provide numerical scores (0-100) for:
        1. Pacing: Flow and rhythm of cuts/transitions
        2. Visual Coherence: How well scenes connect
        3. Technical Quality: Professional polish level
        4. Engagement Impact: How editing affects viewer interest
        
        Editing description: "{editing_text}"
        
        For each criterion:
        1. Carefully analyze the editing description
        2. Consider both explicit quality indicators and implicit effectiveness
        3. Apply your knowledge of professional video editing
        4. Assign a score from 0-100 (higher = better)
        
        Respond in this exact JSON format:
        {{
            "pacing": 80,
            "visual_coherence": 75,
            "technical_quality": 85,
            "engagement_impact": 78,
            "overall_score": 80,
            "reasoning": "brief explanation"
        }}
        """.format(editing_text=editing_text)
        
        result = self._get_gemini_response(prompt)
        
        # If we didn't get valid results, use defaults
        if not result or not isinstance(result, dict):
            return {
                "pacing": 70,
                "visual_coherence": 70,
                "technical_quality": 70,
                "engagement_impact": 70,
                "overall_score": 70,
                "reasoning": "Default scores due to insufficient information"
            }
            
        return result
    
    def _score_voice_with_llm(self, voice_text: str) -> Dict[str, Any]:
        """Score voice and tonality with LLM."""
        prompt = """
        Analyze this voice/tonality description and provide numerical scores (0-100) for:
        1. Clarity: How clear and understandable
        2. Energy Level: Enthusiasm and dynamism
        3. Authenticity: How natural and genuine
        4. Audience Match: Fit with target demographic
        
        Voice description: "{voice_text}"
        
        For each criterion:
        1. Carefully analyze the voice/tonality description
        2. Consider both explicit quality indicators and implicit effectiveness
        3. Apply your knowledge of effective voice performance in videos
        4. Assign a score from 0-100 (higher = better)
        
        Respond in this exact JSON format:
        {{
            "clarity": 85,
            "energy_level": 75,
            "authenticity": 80,
            "audience_match": 78,
            "overall_score": 80,
            "reasoning": "brief explanation"
        }}
        """.format(voice_text=voice_text)
        
        result = self._get_gemini_response(prompt)
        
        # If we didn't get valid results, use defaults
        if not result or not isinstance(result, dict):
            return {
                "clarity": 70,
                "energy_level": 70,
                "authenticity": 70,
                "audience_match": 70,
                "overall_score": 70,
                "reasoning": "Default scores due to insufficient information"
            }
            
        return result
    
    def _get_gemini_response(self, prompt: str) -> Dict[str, Any]:
        """Get structured response from Gemini."""
        try:
            response = self.model.generate_content(prompt)
            if not response or not response.text:
                return {}
            
            # Try to parse the response as JSON
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract JSON from markdown
                json_blocks = re.findall(r'```json\s*(.*?)\s*```', response.text, re.DOTALL)
                if json_blocks:
                    return json.loads(json_blocks[0])
                else:
                    # Try to find a JSON-like structure without code blocks
                    json_pattern = r'\{[\s\S]*\}'
                    json_match = re.search(json_pattern, response.text)
                    if json_match:
                        return json.loads(json_match.group())
                    else:
                        print(f"Failed to parse Gemini response: {response.text}")
                        return {}
                    
        except Exception as e:
            print(f"Error getting Gemini response: {str(e)}")
            return {}
    
    def _extract_numeric_value(self, value: Any) -> str:
        """Extract numeric value from various formats."""
        if isinstance(value, (int, float)):
            return str(value)
        
        # Extract numbers from strings like "85%" or "90 out of 100"
        if isinstance(value, str):
            match = re.search(r'(\d+)', value)
            if match:
                return match.group(1)
        
        return "70"  # Default value
    
    def _get_default_dashboard_data(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """Returns default dashboard data when processing fails."""
        return {
            "metadata": {
                "video_name": analysis_data.get("video_name", "Video Analysis"),
                "id": analysis_data.get("id", ""),
                "timestamp": analysis_data.get("timestamp", "")
            },
            "summary_metrics": {
                "attention_score": {
                    "value": "70",
                    "description": "Overall audience attention retention"
                },
                "engagement": {
                    "value": "70",
                    "description": "Level of audience interaction expected"
                },
                "retention": {
                    "value": "70%",
                    "description": "Percentage of viewers likely to watch to completion"
                }
            },
            "viral_potential": {
                "overall_score": 70,
                "criteria": [
                    {"name": "Visuals", "value": 70, "description": "Default visual assessment"},
                    {"name": "Emotional Impact", "value": 70, "description": "Default emotional impact assessment"},
                    {"name": "Shareability", "value": 70, "description": "Default shareability assessment"},
                    {"name": "Relatability", "value": 70, "description": "Default relatability assessment"},
                    {"name": "Uniqueness", "value": 70, "description": "Default uniqueness assessment"}
                ]
            },
            "social_media_insights": {
                "platform_scores": {
                    "instagram": 70,
                    "tiktok": 70,
                    "youtube_shorts": 70
                },
                "best_performing": "instagram",
                "recommendations": [
                    "Optimize visual composition for mobile viewing",
                    "Include clear calls-to-action",
                    "Add captions for better accessibility"
                ]
            },
            "content_analysis": {
                "hook_effectiveness": {
                    "text": "No hook analysis available",
                    "metrics": {
                        "attention_grab": 70,
                        "curiosity_gap": 70,
                        "relevance": 70,
                        "memorability": 70,
                        "overall_score": 70
                    }
                },
                "editing_quality": {
                    "text": "No editing analysis available",
                    "metrics": {
                        "pacing": 70,
                        "visual_coherence": 70,
                        "technical_quality": 70,
                        "engagement_impact": 70,
                        "overall_score": 70
                    }
                },
                "voice_tonality": {
                    "text": "No voice analysis available",
                    "metrics": {
                        "clarity": 70,
                        "energy_level": 70,
                        "authenticity": 70,
                        "audience_match": 70,
                        "overall_score": 70
                    }
                }
            }
        } 
