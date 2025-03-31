from typing import Dict, Any, List
from datetime import datetime
from metrics_converter import MetricsConverter
import json

class DashboardProcessor:
    """Processes raw analysis data into dashboard-ready format."""
    
    def __init__(self):
        self.metrics_converter = MetricsConverter()
    
    def process_analysis(self, analysis_data):
        """
        Transforms raw analysis data into the format expected by the dashboard.
        
        Args:
            analysis_data: Dictionary containing raw analysis data from Gemini
        
        Returns:
            Dictionary with dashboard-ready data
        """
        try:
            # Use the metrics converter to process all the data in one go
            return self.metrics_converter.process_full_analysis(analysis_data)
        except Exception as e:
            print(f"Error processing analysis data: {str(e)}")
            # Use metrics converter's default dashboard data
            return self.metrics_converter._get_default_dashboard_data(analysis_data)
    
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
            
            # Extract numeric values from the metrics
            try:
                attention = int(metrics["attention_score"]["value"])
            except (ValueError, KeyError, TypeError):
                attention = 70
                
            try:
                engagement = int(metrics["engagement"]["value"])
            except (ValueError, KeyError, TypeError):
                engagement = 70
                
            try:
                retention = int(metrics["retention"]["value"].replace("%", ""))
            except (ValueError, KeyError, TypeError, AttributeError):
                retention = 70
            
            attention_scores.append(attention)
            engagement_scores.append(engagement)
            retention_rates.append(retention)
            timestamps.append(analysis["metadata"]["timestamp"])
            
            # Track platform-specific scores
            for platform in platform_scores:
                if platform in social:
                    platform_scores[platform].append(social[platform])
                else:
                    platform_scores[platform].append(70)  # Default value
        
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
