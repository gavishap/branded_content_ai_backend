import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional

class AnalysisStorage:
    """Handles storage and retrieval of video analysis results."""
    
    def __init__(self, storage_dir: str = "data/analyses"):
        """
        Initialize storage with a directory for saving analyses.
        
        Args:
            storage_dir: Directory path for storing analysis files
        """
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
    
    def save_analysis(self, video_name: str, analysis_data: Dict[str, Any]) -> str:
        """
        Save analysis results to a JSON file.
        
        Args:
            video_name: Name of the analyzed video
            analysis_data: Analysis results dictionary
            
        Returns:
            str: ID of the saved analysis
        """
        # Create a unique ID for this analysis
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        analysis_id = f"{video_name}_{timestamp}"
        
        # Add metadata to the analysis
        analysis_with_metadata = {
            "id": analysis_id,
            "video_name": video_name,
            "timestamp": timestamp,
            "analysis": analysis_data
        }
        
        # Save to file
        file_path = os.path.join(self.storage_dir, f"{analysis_id}.json")
        with open(file_path, 'w') as f:
            json.dump(analysis_with_metadata, f, indent=2)
        
        return analysis_id
    
    def get_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific analysis by ID.
        
        Args:
            analysis_id: ID of the analysis to retrieve
            
        Returns:
            Dict containing the analysis data or None if not found
        """
        file_path = os.path.join(self.storage_dir, f"{analysis_id}.json")
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
    
    def get_all_analyses(self) -> List[Dict[str, Any]]:
        """
        Retrieve all stored analyses.
        
        Returns:
            List of all analysis dictionaries
        """
        analyses = []
        for filename in os.listdir(self.storage_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(self.storage_dir, filename)
                with open(file_path, 'r') as f:
                    analyses.append(json.load(f))
        return sorted(analyses, key=lambda x: x['timestamp'], reverse=True)
    
    def delete_analysis(self, analysis_id: str) -> bool:
        """
        Delete an analysis by ID.
        
        Args:
            analysis_id: ID of the analysis to delete
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        file_path = os.path.join(self.storage_dir, f"{analysis_id}.json")
        try:
            os.remove(file_path)
            return True
        except FileNotFoundError:
            return False 
