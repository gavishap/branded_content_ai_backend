from collections import Counter
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_objects(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes general detection results for object presence and frequency."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    object_counts = Counter()
    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.7 # Confidence for detected objects

    for frame in response.outputs[0].data.frames:
        # Objects are typically in regions for detector models
        for region in frame.data.regions:
            # Detector models often have concepts within regions
            for concept in region.data.concepts:
                 if concept.value >= confidence_threshold:
                    object_counts[concept.name.lower()] += 1
                    # Note: We count each detection instance. If an object persists across
                    # frames, it gets counted multiple times. Tracking requires more logic.

    # Calculate frequency (percentage of frames where *at least one* instance was detected)
    # This requires a different loop structure - TODO: Refine if needed.
    # For now, returning total counts.

    # Get top N detected objects
    top_n = 10
    top_objects = object_counts.most_common(top_n)

    return {
        "total_frames_analyzed": total_frames,
        "confidence_threshold": confidence_threshold,
        "top_detected_objects_by_count": dict(top_objects), # Top N objects by total detection count
        "all_detected_objects_counts": dict(object_counts)
        # TODO: Calculate frequency (% of frames object appeared in)
    } 
