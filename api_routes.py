from flask import Blueprint, request, jsonify, make_response
from datetime import datetime
from typing import Dict, Any
import os
import json
import concurrent.futures
import traceback

# Import S3 utilities
from s3_utils import S3_BUCKET_NAME, s3_client, download_json_from_s3

# Create a blueprint for analysis routes
analysis_bp = Blueprint('analysis', __name__)

# Helper function to add CORS headers to responses
def add_cors_headers(response):
    # Get the origin from the request headers
    origin = request.headers.get('Origin', '')
    
    # List of allowed origins
    allowed_origins = ['https://branded-content-ai.vercel.app', 'http://localhost:3000']
    
    # Check if the request origin is in our list of allowed origins
    if origin in allowed_origins:
        response.headers.set('Access-Control-Allow-Origin', origin)
        response.headers.set('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.set('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.set('Access-Control-Allow-Credentials', 'true')
    
    return response

@analysis_bp.route('/api/saved-analyses', methods=['GET', 'OPTIONS'])
def get_saved_analyses():
    """Get saved analyses list by listing objects in S3 and fetching metadata."""
    # Handle preflight OPTIONS request
    if request.method == 'OPTIONS':
        response = make_response()
        return add_cors_headers(response)

    limit = int(request.args.get('limit', 20))
    skip = int(request.args.get('skip', 0))
    prefix = "analysis-results/"
    print(f"[get_saved_analyses BP] Called with limit={limit}, skip={skip}")

    analyses_list = []
    all_objects_info = []

    try:
        print(f"[get_saved_analyses BP] Listing objects from S3 bucket {S3_BUCKET_NAME} with prefix {prefix}")
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix)

        # --- Log Page by Page --- 
        page_count = 0
        object_count = 0
        for page in pages:
            page_count += 1
            if "Contents" in page:
                page_object_count = len(page['Contents'])
                object_count += page_object_count
                print(f"[get_saved_analyses BP] S3 List Page {page_count}: Found {page_object_count} objects in this page.")
                for obj in page['Contents']:
                    object_key = obj.get('Key')
                    last_modified = obj.get('LastModified')
                    if not object_key:
                        print(f"[get_saved_analyses BP] Warning: Found object without key in page {page_count}")
                        continue
                    # Exclude error files and the prefix key itself
                    if not object_key.endswith("_error.json") and object_key != prefix:
                        if last_modified:
                             all_objects_info.append((object_key, last_modified))
                        else:
                             print(f"[get_saved_analyses BP] Warning: Object {object_key} missing LastModified date.")
            else:
                print(f"[get_saved_analyses BP] S3 List Page {page_count}: No 'Contents' found.")
        # -------------------------
        print(f"[get_saved_analyses BP] Total objects found after filtering prefix/errors: {len(all_objects_info)}")

        # Sort by LastModified date, newest first
        try:
             all_objects_info.sort(key=lambda x: x[1], reverse=True)
             print(f"[get_saved_analyses BP] Successfully sorted {len(all_objects_info)} objects by date.")
        except Exception as sort_e:
            print(f"[get_saved_analyses BP] Error sorting objects: {sort_e}")

        # Apply skip and limit AFTER sorting
        start_index = skip
        end_index = skip + limit
        paginated_keys_with_mod_time = all_objects_info[start_index : end_index]
        paginated_keys = [key for key, mod_time in paginated_keys_with_mod_time]
        print(f"[get_saved_analyses BP] After pagination (skip={skip}, limit={limit}): {len(paginated_keys)} keys to fetch details for.")

        if not paginated_keys:
            print("[get_saved_analyses BP] No keys left after pagination. Returning empty list.")
            response = jsonify({"analyses": [], "total": len(all_objects_info), "limit": limit, "skip": skip, "success": True})
            return add_cors_headers(response)

        print(f"[get_saved_analyses BP] Starting concurrent download for {len(paginated_keys)} analysis JSONs...")
        # Fetch details concurrently
        results = {} # Store results keyed by S3 key
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_key = {executor.submit(download_json_from_s3, S3_BUCKET_NAME, key): key for key in paginated_keys}
            for future in concurrent.futures.as_completed(future_to_key):
                key = future_to_key[future]
                try:
                    analysis_data = future.result()
                    if analysis_data:
                        results[key] = analysis_data
                    else:
                        print(f"[get_saved_analyses BP] Failed to download or parse JSON for key: {key}")
                except Exception as exc:
                    print(f'[get_saved_analyses BP] Error during download/parse future for key {key}: {exc}')

        # Process downloaded results in the original paginated order
        print(f"[get_saved_analyses BP] Processing {len(results)} successfully downloaded results.")
        processed_count = 0
        for key, mod_time in paginated_keys_with_mod_time:
             if key in results:
                 analysis_data = results[key]
                 if isinstance(analysis_data.get("metadata"), dict):
                     metadata = analysis_data["metadata"]
                     analysis_id = metadata.get("id")
                     analysis_name = metadata.get("analysis_name")
                     dt_obj = mod_time
                     timestamp_str_iso = dt_obj.isoformat()
                     formatted_date_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
                     if not analysis_id:
                         print(f"[get_saved_analyses BP] Warning: Missing 'id' in metadata for {key}")
                         analysis_id = key.split('/')[-1].replace('.json', '')
                     analyses_list.append({
                         "id": analysis_id,
                         "analysis_name": analysis_name or f"Analysis {analysis_id[:8]}...",
                         "timestamp": timestamp_str_iso,
                         "formatted_date": formatted_date_str,
                         "source": "S3"
                     })
                     processed_count += 1
                 else:
                     print(f"[get_saved_analyses BP] Warning: Missing or invalid 'metadata' object in downloaded JSON for {key}")

        print(f"[get_saved_analyses BP] Processed {processed_count} analyses. Returning list.")
        response = jsonify({"analyses": analyses_list, "total": len(all_objects_info), "limit": limit, "skip": skip, "success": True})
        return add_cors_headers(response)

    except Exception as e:
        print(f"[get_saved_analyses BP] General error listing analyses from S3: {e}")
        traceback.print_exc()
        response = jsonify({"error": f"Failed to retrieve saved analyses: {str(e)}", "analyses": [], "success": False}), 500
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
        # Get the analysis from S3
        print(f"[get_saved_analysis BP] Attempting to fetch {analysis_id} from S3 (Placeholder - needs implementation)")
        s3_key = f"analysis-results/{analysis_id}.json"
        analysis = download_json_from_s3(S3_BUCKET_NAME, s3_key)

        if not analysis:
            response = jsonify({
                "success": False,
                "error": "Analysis not found in S3"
            }), 404
            return add_cors_headers(response)
        
        # Return the analysis
        response = jsonify({
            "success": True,
            "analysis": analysis
        })
        return add_cors_headers(response)
    except Exception as e:
        print(f"[get_saved_analysis BP] Error fetching from S3: {e}")
        traceback.print_exc()
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
        # Delete the analysis from S3
        s3_key = f"analysis-results/{analysis_id}.json"
        print(f"[delete_saved_analysis BP] Attempting to delete {s3_key} from S3")
        try:
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
            success = True # Assume success if no error
            print(f"[delete_saved_analysis BP] Delete command sent for {s3_key}")
            # Note: delete_object doesn't confirm existence before deleting
        except Exception as s3_e:
            print(f"[delete_saved_analysis BP] Error deleting from S3: {s3_e}")
            success = False

        if not success:
            response = jsonify({
                "success": False,
                "error": "Analysis could not be deleted from S3"
            }), 500 # Maybe 404 if we could confirm it didn't exist?
            return add_cors_headers(response)

        # Return success
        response = jsonify({
            "success": True,
            "message": f"Analysis {analysis_id} deleted successfully from S3"
        })
        return add_cors_headers(response)
    except Exception as e:
        print(f"[delete_saved_analysis BP] General error: {e}")
        traceback.print_exc()
        response = jsonify({
            "success": False,
            "error": str(e)
        }), 500
        return add_cors_headers(response)

# This endpoint is likely unused now as saving happens in the background task
# If needed, it should be updated to trigger the S3 upload process.
# @analysis_bp.route('/api/save-analysis', methods=['POST', 'OPTIONS'])
# def save_new_analysis():
#    ...
