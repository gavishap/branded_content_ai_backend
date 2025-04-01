from collections import Counter, defaultdict
from typing import Dict, Any, Optional, List
from clarifai_grpc.grpc.api import service_pb2

def analyze_concepts(response: service_pb2.MultiOutputResponse, brand_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Analyzes concept recognition results to provide aggregated insights."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.7
    
    # Track in which frames each concept appears
    concept_frames = defaultdict(set)
    brand_frames = defaultdict(set)
    
    for frame in response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        frame_concepts = set()
        
        for concept in frame.data.concepts:
            if concept.value >= confidence_threshold:
                name = concept.name.lower()
                concept_frames[name].add(timestamp)
                frame_concepts.add(name)

        # Check for brand keywords in this frame's concepts
        if brand_keywords:
            for keyword in brand_keywords:
                if keyword.lower() in frame_concepts:
                    brand_frames[keyword.lower()].add(timestamp)

    # Calculate distribution percentages
    concept_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in concept_frames.items()
    }

    brand_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in brand_frames.items()
    }

    # Sort by percentage for clearer output
    sorted_distribution = dict(sorted(
        concept_distribution.items(),
        key=lambda x: x[1],
        reverse=True
    ))

    return {
        "total_frames_analyzed": total_frames,
        "unique_concepts_detected": len(concept_frames),
        "concept_distribution_percent": sorted_distribution,
        "brand_distribution_percent": brand_distribution if brand_keywords else {}
    } 
