from collections import Counter
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_celebrities(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes celebrity detection results."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    celebrity_counts = Counter()
    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.8 # Confidence for detected celebrities

    for frame in response.outputs[0].data.frames:
        # Celebrities are usually in regions
        for region in frame.data.regions:
            # Celebrity model might have concepts within regions
            for concept in region.data.concepts:
                 if concept.value >= confidence_threshold:
                    celebrity_counts[concept.name] += 1 # Keep original case for names
                    # Note: Counts each detection instance.

    # Calculate frequency - TODO

    # Get top N detected celebrities
    top_n = 5
    top_celebrities = celebrity_counts.most_common(top_n)

    return {
        "total_frames_analyzed": total_frames,
        "confidence_threshold": confidence_threshold,
        "top_detected_celebrities_by_count": dict(top_celebrities),
        "all_detected_celebrities_counts": dict(celebrity_counts)
        # TODO: Calculate frequency (% of frames celeb appeared in)
    } 
