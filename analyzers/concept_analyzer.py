from collections import Counter, defaultdict
from typing import Dict, Any, Optional, List
from clarifai_grpc.grpc.api import service_pb2

def analyze_concepts(response: service_pb2.MultiOutputResponse, brand_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Analyzes concept recognition results to provide aggregated insights."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    concept_counts = Counter()
    brand_timestamps = defaultdict(list)
    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.8 # Only count concepts above this confidence

    for frame in response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        frame_concepts = set()
        for concept in frame.data.concepts:
            if concept.value >= confidence_threshold:
                name = concept.name.lower()
                concept_counts[name] += 1
                frame_concepts.add(name)

        # Check for brand keywords in this frame's concepts
        if brand_keywords:
            for keyword in brand_keywords:
                if keyword.lower() in frame_concepts:
                    brand_timestamps[keyword.lower()].append(timestamp)

    # Calculate frequency distribution (percentage of frames concept appeared in)
    concept_frequency = {name: round((count / total_frames) * 100, 2)
                          for name, count in concept_counts.items()}

    # Get top N concepts
    top_n = 15
    top_concepts = concept_counts.most_common(top_n)

    return {
        "total_frames_analyzed": total_frames,
        "confidence_threshold": confidence_threshold,
        "top_concepts": dict(top_concepts), # Top N concepts and their frame counts
        "concept_frequency_percent": concept_frequency, # Percentage of frames each concept appeared in
        "brand_appearance_timestamps_ms": dict(brand_timestamps)
    } 
