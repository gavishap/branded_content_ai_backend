from collections import Counter, defaultdict
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_celebrities(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes celebrity detection results."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.7
    
    # Track in which frames each celebrity appears
    celebrity_frames = defaultdict(set)
    
    for frame in response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        for region in frame.data.regions:
            for concept in region.data.concepts:
                if concept.value >= confidence_threshold:
                    name = concept.name  # Keep original case for celebrity names
                    celebrity_frames[name].add(timestamp)

    # Calculate distribution percentages
    celebrity_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in celebrity_frames.items()
    }

    # Sort by percentage for clearer output
    sorted_distribution = dict(sorted(
        celebrity_distribution.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    return {
        "total_frames_analyzed": total_frames,
        "unique_celebrities_detected": len(celebrity_frames),
        "celebrity_distribution_percent": sorted_distribution
    } 
