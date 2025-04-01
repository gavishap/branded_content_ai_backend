from collections import Counter, defaultdict
from typing import Dict, Any

def analyze_concepts(response) -> Dict[str, Any]:
    """Analyzes concept recognition results from the general recognition model."""
    if not response or not response.outputs:
        return {
            "total_frames_analyzed": 0,
            "unique_concepts_detected": 0,
            "concept_distribution_percent": {}
        }

    # Track which frames each concept appears in
    concept_frames = defaultdict(list)
    total_frames = len(response.outputs[0].data.frames)

    # Process each frame
    for frame in response.outputs[0].data.frames:
        frame_time = frame.frame_info.time
        for concept in frame.data.concepts:
            if concept.value >= 0.7:  # Confidence threshold
                concept_frames[concept.name].append(frame_time)

    # Calculate distribution percentages
    distribution = {}
    for concept, frames in concept_frames.items():
        percentage = (len(frames) / total_frames) * 100
        distribution[concept] = round(percentage, 2)

    # Sort by percentage (highest first)
    sorted_distribution = dict(sorted(distribution.items(), key=lambda x: x[1], reverse=True))

    return {
        "total_frames_analyzed": total_frames,
        "unique_concepts_detected": len(concept_frames),
        "concept_distribution_percent": sorted_distribution
    } 
