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
        
    def convert_to_metrics(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert natural language insights into numerical metrics.
        
        Args:
            analysis_data: Raw analysis data containing textual insights
            
        Returns:
            Dict containing numerical metrics and scores
        """
        try:
            detailed = analysis_data.get("Detailed Analysis", {}).get("In-depth Video Analysis", {})
            if not detailed:
                raise ValueError("Missing required analysis sections")
            
            metrics = {
                "hook_effectiveness": self._score_hook(detailed.get("Hook", "")),
                "editing_quality": self._score_editing(detailed.get("Editing", "")),
                "voice_tonality": self._score_voice(detailed.get("Tonality", "")),
                "viral_metrics": self._score_viral_potential(detailed.get("Viral Potential", {})),
                "social_metrics": self._score_social_strengths(detailed.get("Core Strengths", {}))
            }
            
            return metrics
            
        except Exception as e:
            print(f"Error converting metrics: {str(e)}")
            # Return default metrics if conversion fails
            return self._get_default_metrics()
    
    def _score_hook(self, hook_text: str) -> Dict[str, Any]:
        """Score hook effectiveness on multiple dimensions."""
        prompt = f"""
        Analyze this video hook description and provide numerical scores (0-100) for:
        1. Attention Grab: How quickly it captures attention
        2. Curiosity Gap: How well it creates intrigue
        3. Relevance: How well it connects to target audience
        4. Memorability: How likely viewers remember it
        
        Hook description: "{hook_text}"
        
        Respond in this exact JSON format:
        {{
            "attention_grab": <score>,
            "curiosity_gap": <score>,
            "relevance": <score>,
            "memorability": <score>,
            "overall_score": <average of all scores>,
            "reasoning": "<brief explanation>"
        }}
        """
        
        return self._get_gemini_response(prompt)
    
    def _score_editing(self, editing_text: str) -> Dict[str, Any]:
        """Score editing quality metrics."""
        prompt = f"""
        Analyze this video editing description and provide numerical scores (0-100) for:
        1. Pacing: Flow and rhythm of cuts/transitions
        2. Visual Coherence: How well scenes connect
        3. Technical Quality: Professional polish level
        4. Engagement Impact: How editing affects viewer interest
        
        Editing description: "{editing_text}"
        
        Respond in this exact JSON format:
        {{
            "pacing": <score>,
            "visual_coherence": <score>,
            "technical_quality": <score>,
            "engagement_impact": <score>,
            "overall_score": <average of all scores>,
            "reasoning": "<brief explanation>"
        }}
        """
        
        return self._get_gemini_response(prompt)
    
    def _score_voice(self, voice_text: str) -> Dict[str, Any]:
        """Score voice and tonality metrics."""
        prompt = f"""
        Analyze this voice/tonality description and provide numerical scores (0-100) for:
        1. Clarity: How clear and understandable
        2. Energy Level: Enthusiasm and dynamism
        3. Authenticity: How natural and genuine
        4. Audience Match: Fit with target demographic
        
        Voice description: "{voice_text}"
        
        Respond in this exact JSON format:
        {{
            "clarity": <score>,
            "energy_level": <score>,
            "authenticity": <score>,
            "audience_match": <score>,
            "overall_score": <average of all scores>,
            "reasoning": "<brief explanation>"
        }}
        """
        
        return self._get_gemini_response(prompt)
    
    def _score_viral_potential(self, viral_criteria: Dict[str, str]) -> Dict[str, Any]:
        """Score viral potential across multiple dimensions."""
        prompt = f"""
        Analyze these viral criteria descriptions and provide numerical scores (0-100) for each:
        
        Visuals: "{viral_criteria.get('Visuals', '')}"
        Emotion: "{viral_criteria.get('Emotion', '')}"
        Shareability: "{viral_criteria.get('Shareability', '')}"
        Relatability: "{viral_criteria.get('Relatability', '')}"
        Uniqueness: "{viral_criteria.get('Uniqueness', '')}"
        
        Respond in this exact JSON format:
        {{
            "visuals": <score>,
            "emotional_connection": <score>,
            "shareability": <score>,
            "relatability": <score>,
            "uniqueness": <score>,
            "viral_probability": <weighted average favoring shareability>,
            "reasoning": "<brief explanation>"
        }}
        """
        
        return self._get_gemini_response(prompt)
    
    def _score_social_strengths(self, social_strengths: Dict[str, str]) -> Dict[str, Any]:
        """Score social media performance indicators."""
        prompt = f"""
        Analyze these social media strengths and provide numerical scores (0-100) for each:
        
        Visual Appeal: "{social_strengths.get('Visuals', '')}"
        Content Quality: "{social_strengths.get('Content', '')}"
        Pacing: "{social_strengths.get('Pacing', '')}"
        Value Proposition: "{social_strengths.get('Value', '')}"
        Call to Action: "{social_strengths.get('CTA', '')}"
        
        Also predict platform-specific performance scores.
        
        Respond in this exact JSON format:
        {{
            "visual_appeal": <score>,
            "content_quality": <score>,
            "pacing": <score>,
            "value_prop": <score>,
            "cta_effectiveness": <score>,
            "platform_fit": {{
                "tiktok": <score>,
                "instagram": <score>,
                "youtube_shorts": <score>
            }},
            "reasoning": "<brief explanation>"
        }}
        """
        
        return self._get_gemini_response(prompt)
    
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
                    print(f"Failed to parse Gemini response: {response.text}")
                    return {}
                    
        except Exception as e:
            print(f"Error getting Gemini response: {str(e)}")
            return {}

    def _get_default_metrics(self) -> Dict[str, Any]:
        """
        Returns default metrics when conversion fails.
        """
        return {
            "hook_effectiveness": {
                "overall_score": 70,
                "attention_grab": 70,
                "clarity": 70,
                "memorability": 70
            },
            "editing_quality": {
                "overall_score": 70,
                "pacing": 70,
                "transitions": 70,
                "visual_flow": 70
            },
            "voice_tonality": {
                "overall_score": 70,
                "clarity": 70,
                "engagement": 70,
                "authenticity": 70
            },
            "viral_metrics": {
                "viral_probability": 70,
                "visuals": 70,
                "emotional_connection": 70,
                "shareability": 70,
                "relatability": 70,
                "uniqueness": 70,
                "platform_fit": {
                    "tiktok": 70,
                    "instagram": 70,
                    "youtube_shorts": 70
                }
            },
            "social_metrics": {
                "overall_engagement": 70,
                "visual_appeal": 70,
                "content_quality": 70,
                "pacing_score": 70,
                "value_delivery": 70,
                "cta_effectiveness": 70,
                "platform_fit": {
                    "tiktok": 70,
                    "instagram": 70,
                    "youtube_shorts": 70
                }
            }
        } 
