import os
import json
from datetime import datetime
import uuid
from typing import Dict, List, Optional, Any

# Define the storage path
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ANALYSES_DIR = os.path.join(DATA_DIR, "analyses")

# Ensure directories exist
os.makedirs(ANALYSES_DIR, exist_ok=True)

class AnalysisStorage:
    """
    Handles storage and retrieval of analysis data.
    This class provides methods to save, retrieve, list, and delete analyses.
    """
    
    @staticmethod
    def generate_id(content_name: str) -> str:
        """Generate a unique ID for an analysis based on content name and timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in content_name)
        return f"{sanitized_name}_{timestamp}"
    
    @staticmethod
    def save_analysis(analysis_data: Dict[str, Any], content_name: str = None, analysis_id: str = None) -> str:
        """
        Save an analysis to the file system.
        
        Args:
            analysis_data: The analysis data to save
            content_name: Name of the content (video filename or URL identifier)
            analysis_id: Optional custom ID. If not provided, one will be generated.
            
        Returns:
            The ID of the saved analysis
        """
        # Generate ID if not provided
        if not analysis_id:
            if not content_name:
                content_name = f"analysis_{uuid.uuid4().hex[:8]}"
            analysis_id = AnalysisStorage.generate_id(content_name)
        
        # Prepare the full analysis object with metadata
        full_analysis = {
            "id": analysis_id,
            "content_name": content_name,
            "timestamp": datetime.now().isoformat(),
            "analysis_data": analysis_data
        }
        
        # Save to file
        filename = f"{analysis_id}.json"
        filepath = os.path.join(ANALYSES_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(full_analysis, f, indent=2, ensure_ascii=False)
            
        print(f"Analysis saved to {filepath}")
        return analysis_id
    
    @staticmethod
    def get_analysis(analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an analysis by ID.
        
        Args:
            analysis_id: The ID of the analysis to retrieve
            
        Returns:
            The analysis data or None if not found
        """
        filepath = os.path.join(ANALYSES_DIR, f"{analysis_id}.json")
        
        if not os.path.exists(filepath):
            return None
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading analysis {analysis_id}: {e}")
            return None
    
    @staticmethod
    def list_analyses(limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
        """
        List available analyses with pagination.
        
        Args:
            limit: Maximum number of analyses to return
            skip: Number of analyses to skip
            
        Returns:
            List of analysis metadata
        """
        analyses = []
        
        # Get all JSON files in the analyses directory
        try:
            files = [f for f in os.listdir(ANALYSES_DIR) if f.endswith('.json')]
            
            # Sort by modification time (newest first)
            files.sort(key=lambda x: os.path.getmtime(os.path.join(ANALYSES_DIR, x)), reverse=True)
            
            # Apply pagination
            paginated_files = files[skip:skip+limit]
            
            # Load each analysis metadata
            for filename in paginated_files:
                filepath = os.path.join(ANALYSES_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        analysis = json.load(f)
                        analyses.append({
                            "id": analysis.get("id", filename.replace(".json", "")),
                            "content_name": analysis.get("content_name", "Unknown"),
                            "timestamp": analysis.get("timestamp", os.path.getmtime(filepath)),
                            "thumbnail": analysis.get("thumbnail", None)
                        })
                except Exception as e:
                    print(f"Error loading analysis metadata for {filename}: {e}")
        except Exception as e:
            print(f"Error listing analyses: {e}")
            
        return analyses
    
    @staticmethod
    def delete_analysis(analysis_id: str) -> bool:
        """
        Delete an analysis by ID.
        
        Args:
            analysis_id: The ID of the analysis to delete
            
        Returns:
            True if successful, False otherwise
        """
        filepath = os.path.join(ANALYSES_DIR, f"{analysis_id}.json")
        
        if not os.path.exists(filepath):
            return False
            
        try:
            os.remove(filepath)
            return True
        except Exception as e:
            print(f"Error deleting analysis {analysis_id}: {e}")
            return False
    
    @staticmethod
    def update_analysis(analysis_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an existing analysis with new data.
        
        Args:
            analysis_id: The ID of the analysis to update
            update_data: The data to update
            
        Returns:
            True if successful, False otherwise
        """
        # Get the existing analysis
        analysis = AnalysisStorage.get_analysis(analysis_id)
        
        if not analysis:
            return False
            
        # Update the analysis with new data
        for key, value in update_data.items():
            if key == "analysis_data" and isinstance(value, dict) and isinstance(analysis.get("analysis_data", {}), dict):
                # Merge nested analysis_data dictionaries
                analysis["analysis_data"].update(value)
            else:
                analysis[key] = value
        
        # Save the updated analysis
        filepath = os.path.join(ANALYSES_DIR, f"{analysis_id}.json")
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error updating analysis {analysis_id}: {e}")
            return False

# For direct testing
if __name__ == "__main__":
    # Test save
    test_id = AnalysisStorage.save_analysis(
        {"test": "data", "metrics": {"score": 85}},
        "test_video"
    )
    print(f"Saved test analysis with ID: {test_id}")
    
    # Test get
    retrieved = AnalysisStorage.get_analysis(test_id)
    print(f"Retrieved analysis: {retrieved is not None}")
    
    # Test list
    analyses = AnalysisStorage.list_analyses(limit=5)
    print(f"Listed {len(analyses)} analyses")
    
    # Test update
    updated = AnalysisStorage.update_analysis(
        test_id,
        {"analysis_data": {"metrics": {"new_score": 90}}}
    )
    print(f"Updated analysis: {updated}")
    
    # Test delete
    deleted = AnalysisStorage.delete_analysis(test_id)
    print(f"Deleted test analysis: {deleted}") 
