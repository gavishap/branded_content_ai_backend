from collections import Counter, defaultdict
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_objects(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes general detection results for object presence and frequency."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.7
    
    # Track in which frames each object appears
    object_frames = defaultdict(set)
    
    for frame in response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        for region in frame.data.regions:
            for concept in region.data.concepts:
                if concept.value >= confidence_threshold:
                    name = concept.name.lower()
                    object_frames[name].add(timestamp)

    # Calculate distribution percentages
    object_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in object_frames.items()
    }

    # Sort by percentage for clearer output
    sorted_distribution = dict(sorted(
        object_distribution.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    return {
        "total_frames_analyzed": total_frames,
        "unique_objects_detected": len(object_frames),
        "object_distribution_percent": sorted_distribution
    } 
