from collections import Counter, defaultdict
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_faces(model_responses: Dict[str, service_pb2.MultiOutputResponse]) -> Dict[str, Any]:
    """Analyzes face model results to provide aggregated insights."""
    if not model_responses:
        return {"error": "No face model responses"}

   

    # Get frame count from any response (they should all have same frame count)
    total_frames = len(next(iter(model_responses.values())).outputs[0].data.frames)
    confidence_threshold = 0.3  # Lowered from 0.7 to catch more face attributes
    
    # Track in which frames each attribute appears
    sentiment_frames = defaultdict(set)
    age_frames = defaultdict(set)
    gender_frames = defaultdict(set)
    multiculturality_frames = defaultdict(set)
    
    # Process each frame from each model
    for model_name, response in model_responses.items():
        if not response or not response.outputs:
            continue
            
        for frame in response.outputs[0].data.frames:
            timestamp = frame.frame_info.time
            
            # Process concepts based on model type
            for concept in frame.data.concepts:
                if concept.value >= confidence_threshold:
                    name = concept.name.lower()
                    
                    if model_name == "face_sentiment":
                        sentiment_frames[name].add(timestamp)
                    elif model_name == "face_age":
                        age_frames[name].add(timestamp)
                    elif model_name == "face_gender":
                        gender_frames[name].add(timestamp)
                    elif model_name == "face_multiculturality":
                        multiculturality_frames[name].add(timestamp)

    # Calculate distribution percentages
    sentiment_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in sentiment_frames.items()
    }

    age_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in age_frames.items()
    }

    gender_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in gender_frames.items()
    }

    multiculturality_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in multiculturality_frames.items()
    }

    # Sort by percentage for clearer output
    sorted_sentiment = dict(sorted(sentiment_distribution.items(), key=lambda x: x[1], reverse=True))
    sorted_age = dict(sorted(age_distribution.items(), key=lambda x: x[1], reverse=True))
    sorted_gender = dict(sorted(gender_distribution.items(), key=lambda x: x[1], reverse=True))
    sorted_multiculturality = dict(sorted(multiculturality_distribution.items(), key=lambda x: x[1], reverse=True))

    return {
        "total_frames_analyzed": total_frames,
        "frames_with_faces_percent": round((len(sentiment_frames) / total_frames) * 100, 2),
        "attribute_distribution_percent": {
            "sentiment": sorted_sentiment,
            "age": sorted_age,
            "gender": sorted_gender,
            "multiculturality": sorted_multiculturality
        }
    } 
