from flask import Blueprint, request, jsonify, make_response
from mongodb_storage import MongoDBStorage
from datetime import datetime
from typing import Dict, Any
import os
import json

# Create a blueprint for analysis routes
analysis_bp = Blueprint('analysis', __name__)

# Helper function to add CORS headers to responses
def add_cors_headers(response):
    response.headers.set('Access-Control-Allow-Origin', 'https://branded-content-ai.vercel.app')
    response.headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.set('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.set('Access-Control-Allow-Credentials', 'true')
    return response

@analysis_bp.route('/api/saved-analyses', methods=['GET', 'OPTIONS'])
def get_saved_analyses():
    """
    Get a list of all saved analyses with pagination.
    
    Query parameters:
    - limit: Maximum number of analyses to return (default: 20)
    - skip: Number of analyses to skip (default: 0)
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
        
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
            
            # Return the list of analyses with CORS headers
            response = jsonify({
                "success": True,
                "analyses": analyses,
                "total": total_count,
                "limit": limit,
                "skip": skip,
                "has_more": skip + len(analyses) < total_count
            })
            return add_cors_headers(response)
            
        except Exception as db_error:
            print(f"Database error in get_saved_analyses: {str(db_error)}")
            # Return empty list on database errors
            response = jsonify({
                "success": True,  # Return success:true to prevent frontend errors
                "analyses": [],
                "total": 0,
                "limit": limit,
                "skip": skip,
                "has_more": False,
                "message": "Could not retrieve analyses from database"
            })
            return add_cors_headers(response)
            
    except Exception as e:
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        return add_cors_headers(response)

@analysis_bp.route('/api/saved-analyses/<analysis_id>', methods=['GET', 'OPTIONS'])
def get_saved_analysis(analysis_id):
    """
    Get a specific analysis by ID.
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
        
    try:
        # Get the analysis from MongoDB
        analysis = MongoDBStorage.get_analysis(analysis_id)
        
        if not analysis:
            response = jsonify({
                "success": False,
                "error": "Analysis not found"
            }), 404
            return add_cors_headers(response)
        
        # Return the analysis
        response = jsonify({
            "success": True,
            "analysis": analysis
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        return add_cors_headers(response)

@analysis_bp.route('/api/saved-analyses/<analysis_id>', methods=['DELETE', 'OPTIONS'])
def delete_saved_analysis(analysis_id):
    """
    Delete a specific analysis by ID.
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
        
    try:
        # Delete the analysis from MongoDB
        success = MongoDBStorage.delete_analysis(analysis_id)
        
        if not success:
            response = jsonify({
                "success": False,
                "error": "Analysis not found or could not be deleted"
            }), 404
            return add_cors_headers(response)
        
        # Return success
        response = jsonify({
            "success": True,
            "message": f"Analysis {analysis_id} deleted successfully"
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        return add_cors_headers(response)

@analysis_bp.route('/api/save-analysis', methods=['POST', 'OPTIONS'])
def save_new_analysis():
    """
    Save a new analysis.
    
    Request body:
    - analysis_data: The analysis data to save
    - content_name: Name of the content (optional)
    """
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)
        
    try:
        # Get data from request
        data = request.json
        
        if not data or not isinstance(data, dict):
            response = jsonify({
                "success": False,
                "error": "Invalid request data"
            }), 400
            return add_cors_headers(response)
        
        analysis_data = data.get('analysis_data')
        content_name = data.get('content_name', 'Untitled Analysis')
        
        if not analysis_data:
            response = jsonify({
                "success": False,
                "error": "Missing analysis_data"
            }), 400
            return add_cors_headers(response)
        
        # Save the analysis to MongoDB
        analysis_id = MongoDBStorage.save_analysis(analysis_data, content_name)
        
        # Return success and the new analysis ID
        response = jsonify({
            "success": True,
            "analysis_id": analysis_id,
            "message": "Analysis saved successfully"
        })
        return add_cors_headers(response)
    except Exception as e:
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        return add_cors_headers(response) 
