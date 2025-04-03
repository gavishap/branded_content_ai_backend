import os
import json
from datetime import datetime
import uuid
from typing import Dict, List, Optional, Any
from pymongo import MongoClient
from dotenv import load_dotenv
from bson.objectid import ObjectId
import sys
import pymongo
import traceback

# Load environment variables
load_dotenv()

# MongoDB connection details
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "branded_content_ai")
MONGODB_ANALYSES_COLLECTION = os.getenv("MONGODB_ANALYSES_COLLECTION", "analyses")

# Fallback local storage
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ANALYSES_DIR = os.path.join(DATA_DIR, "analyses")

# Create data directories if they don't exist
os.makedirs(ANALYSES_DIR, exist_ok=True)

class MongoDBStorage:
    """
    Handles storage and retrieval of analysis data using MongoDB.
    """
    
    _client = None
    _db = None
    _collection = None
    
    @classmethod
    def get_collection(cls, server_selection_timeout_ms=1000, connect_timeout_ms=1000, socket_timeout_ms=1000):
        """
        Get MongoDB collection for analyses.
        
        Args:
            server_selection_timeout_ms: Timeout for server selection in milliseconds
            connect_timeout_ms: Timeout for connection establishment in milliseconds
            socket_timeout_ms: Timeout for socket operations in milliseconds
            
        Returns:
            MongoDB collection
        """
        # Initialize client if not already initialized
        if cls._client is None:
            try:
                # Add SSL parameters to URI if they're not already present
                uri = MONGODB_URI
                if '?' in uri:
                    if 'tlsAllowInvalidCertificates=true' not in uri:
                        uri += '&tlsAllowInvalidCertificates=true'
                else:
                    uri += '?tlsAllowInvalidCertificates=true'
                    
                print(f"Connecting to MongoDB with modified URI")
                
                # When deployed on Heroku, we need to allow invalid certs
                # But we can't use ssl_cert_reqs as it's not supported in this version
                cls._client = MongoClient(
                    uri, 
                    serverSelectionTimeoutMS=server_selection_timeout_ms,
                    connectTimeoutMS=connect_timeout_ms,
                    socketTimeoutMS=socket_timeout_ms,
                    ssl=True
                    # Remove the ssl_cert_reqs parameter as it's not supported
                    # ssl_cert_reqs=False  # Don't verify SSL certificate
                )
                
                # Test connection
                try:
                    cls._client.admin.command('ping')
                    print("MongoDB connection successful")
                except Exception as e:
                    print(f"Warning: Ping test failed, but continuing: {e}")
                    
            except Exception as e:
                print(f"Error initializing MongoDB client: {e}", file=sys.stderr)
                traceback.print_exc()
                raise
        
        # Get database - if database doesn't exist, MongoDB will create it
        db = cls._client[MONGODB_DB]
        
        # Get collection - if collection doesn't exist, MongoDB will create it
        collection = db[MONGODB_ANALYSES_COLLECTION]
        
        return collection
    
    @classmethod
    def close_connection(cls):
        """Close the MongoDB connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._db = None
            cls._collection = None
            print("MongoDB connection closed")
    
    @staticmethod
    def generate_id(content_name: str) -> str:
        """Generate a unique ID for an analysis based on content name and timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_name = ''.join(c if c.isalnum() or c in ['-', '_'] else '_' for c in content_name)
        return f"{sanitized_name}_{timestamp}"
    
    @classmethod
    def save_analysis(cls, analysis_data: Dict[str, Any], content_name: str = None, analysis_id: str = None) -> str:
        """
        Save an analysis to MongoDB.
        
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
            analysis_id = cls.generate_id(content_name)
        
        # Prepare the full analysis object with metadata
        full_analysis = {
            "id": analysis_id,
            "content_name": content_name,
            "timestamp": datetime.now().isoformat(),
            "analysis_data": analysis_data
        }
        
        # Get collection and save document
        collection = cls.get_collection()
        
        try:
            # Check if document already exists with this ID
            existing = collection.find_one({"id": analysis_id})
            if existing:
                # Update existing document
                collection.update_one(
                    {"id": analysis_id},
                    {"$set": full_analysis}
                )
            else:
                # Insert new document
                collection.insert_one(full_analysis)
                
            print(f"Analysis saved to MongoDB with ID: {analysis_id}")
        except Exception as e:
            print(f"Error saving to MongoDB: {e}", file=sys.stderr)
            
        return analysis_id
    
    @classmethod
    def get_analysis(cls, analysis_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve an analysis by ID.
        
        Args:
            analysis_id: The ID of the analysis to retrieve
            
        Returns:
            The analysis data or None if not found
        """
        if not analysis_id:
            return None
            
        collection = cls.get_collection()
        
        try:
            # Find document by ID
            result = collection.find_one({"id": analysis_id})
            
            if result:
                # Convert ObjectId to string for JSON serialization
                if "_id" in result and isinstance(result["_id"], ObjectId):
                    result["_id"] = str(result["_id"])
                return result
        except Exception as e:
            print(f"Error retrieving analysis {analysis_id}: {e}", file=sys.stderr)
            
        return None
    
    @classmethod
    def list_analyses(cls, limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
        """
        List available analyses with pagination.
        
        Args:
            limit: Maximum number of analyses to return
            skip: Number of analyses to skip
            
        Returns:
            List of analysis metadata
        """
        try:
            # Set MongoDB client options with timeouts
            if cls._client is None:
                # Configure the client with timeouts to prevent hanging
                print(f"Connecting to MongoDB with timeouts: {MONGODB_URI}")
                cls._client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=1000,  # 1 second timeout
                    connectTimeoutMS=1000,
                    socketTimeoutMS=1000
                )
                
            # Use the existing get_collection method which has proper error handling
            collection = cls.get_collection()
            
            # Get total count for debugging
            total_count = collection.count_documents({})
            print(f"Total analyses in collection: {total_count}")
            
            # If we have documents, fetch them with pagination
            analyses = []
            if total_count > 0:
                # Query for all analyses, sorted by timestamp (newest first)
                cursor = collection.find({}).sort("timestamp", -1).skip(skip).limit(limit)
                
                for doc in cursor:
                    # Convert ObjectId to string for JSON serialization
                    if "_id" in doc and isinstance(doc["_id"], ObjectId):
                        doc["_id"] = str(doc["_id"])
                        
                    # Format timestamp for display if needed
                    timestamp = doc.get("timestamp")
                    formatted_date = None
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp)
                            formatted_date = dt.strftime("%B %d, %Y")
                        except (ValueError, TypeError):
                            formatted_date = None
                    
                    # Add analysis to result list with key fields
                    analyses.append({
                        "id": doc.get("id"),
                        "content_name": doc.get("content_name", "Unknown"),
                        "timestamp": timestamp,
                        "thumbnail": doc.get("thumbnail"),
                        "formatted_date": formatted_date or doc.get("formatted_date")
                    })
            
            print(f"Listed {len(analyses)} analyses")
            return analyses
            
        except pymongo.errors.ServerSelectionTimeoutError:
            print("MongoDB server selection timeout. The database may be unreachable.")
            return []
        except pymongo.errors.ConnectionFailure:
            print("Failed to connect to MongoDB. The database may be unreachable.")
            return []
        except Exception as e:
            print(f"Error listing analyses: {e}", file=sys.stderr)
            traceback.print_exc()
            return []
    
    @classmethod
    def delete_analysis(cls, analysis_id: str) -> bool:
        """
        Delete an analysis by ID.
        
        Args:
            analysis_id: The ID of the analysis to delete
            
        Returns:
            True if successful, False otherwise
        """
        collection = cls.get_collection()
        
        # Delete document by ID
        result = collection.delete_one({"id": analysis_id})
        
        # Return True if document was deleted
        return result.deleted_count > 0
    
    @classmethod
    def update_analysis(cls, analysis_id: str, update_data: Dict[str, Any]) -> bool:
        """
        Update an existing analysis with new data.
        
        Args:
            analysis_id: The ID of the analysis to update
            update_data: The data to update
            
        Returns:
            True if successful, False otherwise
        """
        collection = cls.get_collection()
        
        # Get existing document
        existing = collection.find_one({"id": analysis_id})
        if not existing:
            return False
            
        # Prepare update data
        update_fields = {}
        
        # Update analysis_data if provided
        if "analysis_data" in update_data and isinstance(update_data["analysis_data"], dict):
            if "analysis_data" not in existing:
                existing["analysis_data"] = {}
                
            # Merge analysis_data
            update_fields["analysis_data"] = {**existing["analysis_data"], **update_data["analysis_data"]}
            
        # Update other fields
        for key, value in update_data.items():
            if key != "analysis_data":
                update_fields[key] = value
                
        # Update document
        if update_fields:
            result = collection.update_one(
                {"id": analysis_id},
                {"$set": update_fields}
            )
            return result.modified_count > 0
            
        return False
        
    @classmethod
    def count_analyses(cls) -> int:
        """
        Count the total number of analyses in the database.
        
        Returns:
            The total count of analyses
        """
        collection = cls.get_collection()
        return collection.count_documents({})

# For direct testing
if __name__ == "__main__":
    try:
        # Test connection
        print("Testing MongoDB connection...")
        collection = MongoDBStorage.get_collection()
        print(f"Connected to MongoDB. Collection: {MONGODB_ANALYSES_COLLECTION}")
        
        # Test save
        test_id = MongoDBStorage.save_analysis(
            {"test": "data", "metrics": {"score": 85}},
            "test_video"
        )
        print(f"Saved test analysis with ID: {test_id}")
        
        # Test list
        analyses = MongoDBStorage.list_analyses(limit=5)
        print(f"Listed {len(analyses)} analyses")
        
        # Test count
        count = MongoDBStorage.count_analyses()
        print(f"Total analyses in database: {count}")
        
        # Test get
        retrieved = MongoDBStorage.get_analysis(test_id)
        print(f"Retrieved analysis: {retrieved is not None}")
        
        # Test update
        updated = MongoDBStorage.update_analysis(
            test_id,
            {"analysis_data": {"metrics": {"new_score": 90}}}
        )
        print(f"Updated analysis: {updated}")
        
        # Verify update
        updated_analysis = MongoDBStorage.get_analysis(test_id)
        if updated_analysis and updated_analysis.get("analysis_data", {}).get("metrics", {}).get("new_score") == 90:
            print("Update verification successful")
        else:
            print("Update verification failed")
        
        # Test delete
        deleted = MongoDBStorage.delete_analysis(test_id)
        print(f"Deleted test analysis: {deleted}")
        
    finally:
        # Close connection
        MongoDBStorage.close_connection() 
