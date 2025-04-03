from flask import Blueprint, request, jsonify
from mongodb_storage import MongoDBStorage
from datetime import datetime
from typing import Dict, Any
import os
import json

# Create a blueprint for analysis routes
analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/api/saved-analyses', methods=['GET'])
def get_saved_analyses():
    """
    Get a list of all saved analyses with pagination.
    
    Query parameters:
    - limit: Maximum number of analyses to return (default: 20)
    - skip: Number of analyses to skip (default: 0)
    """
    try:
        limit = int(request.args.get('limit', 20))
        skip = int(request.args.get('skip', 0))
        
        # Get analyses from MongoDB
        try:
            analyses = MongoDBStorage.list_analyses(limit=limit, skip=skip)
            
            # Format timestamps nicely for display
            for analysis in analyses:
                if isinstance(analysis.get('timestamp'), str):
                    try:
                        dt = datetime.fromisoformat(analysis['timestamp'])
                        analysis['formatted_date'] = dt.strftime("%B %d, %Y %I:%M %p")
                    except ValueError:
                        analysis['formatted_date'] = analysis['timestamp']
                else:
                    analysis['formatted_date'] = "Unknown date"
            
            # Get total count or default to length of analyses if count fails
            try:
                total_count = MongoDBStorage.count_analyses()
            except:
                total_count = len(analyses)
            
            # Return the list of analyses
            return jsonify({
                "success": True,
                "analyses": analyses,
                "total": total_count,
                "limit": limit,
                "skip": skip,
                "has_more": skip + len(analyses) < total_count
            })
        except Exception as db_error:
            print(f"Database error in get_saved_analyses: {str(db_error)}")
            # Return empty list on database errors
            return jsonify({
                "success": True,  # Return success:true to prevent frontend errors
                "analyses": [],
                "total": 0,
                "limit": limit,
                "skip": skip,
                "has_more": False,
                "message": "Could not retrieve analyses from database"
            })
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@analysis_bp.route('/api/saved-analyses/<analysis_id>', methods=['GET'])
def get_saved_analysis(analysis_id):
    """
    Get a specific analysis by ID.
    """
    try:
        # Get the analysis from MongoDB
        analysis = MongoDBStorage.get_analysis(analysis_id)
        
        if not analysis:
            return jsonify({
                "success": False,
                "error": "Analysis not found"
            }), 404
        
        # Return the analysis
        return jsonify({
            "success": True,
            "analysis": analysis
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@analysis_bp.route('/api/saved-analyses/<analysis_id>', methods=['DELETE'])
def delete_saved_analysis(analysis_id):
    """
    Delete a specific analysis by ID.
    """
    try:
        # Delete the analysis from MongoDB
        success = MongoDBStorage.delete_analysis(analysis_id)
        
        if not success:
            return jsonify({
                "success": False,
                "error": "Analysis not found or could not be deleted"
            }), 404
        
        # Return success
        return jsonify({
            "success": True,
            "message": f"Analysis {analysis_id} deleted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@analysis_bp.route('/api/save-analysis', methods=['POST'])
def save_new_analysis():
    """
    Save a new analysis.
    
    Request body:
    - analysis_data: The analysis data to save
    - content_name: Name of the content (optional)
    """
    try:
        # Get data from request
        data = request.json
        
        if not data or not isinstance(data, dict):
            return jsonify({
                "success": False,
                "error": "Invalid request data"
            }), 400
        
        analysis_data = data.get('analysis_data')
        content_name = data.get('content_name', 'Untitled Analysis')
        
        if not analysis_data:
            return jsonify({
                "success": False,
                "error": "Missing analysis_data"
            }), 400
        
        # Save the analysis to MongoDB
        analysis_id = MongoDBStorage.save_analysis(analysis_data, content_name)
        
        # Return success and the new analysis ID
        return jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "message": "Analysis saved successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500 
