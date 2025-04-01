from collections import Counter, defaultdict
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_colors(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes color recognition results to provide aggregated insights."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    total_frames = len(response.outputs[0].data.frames)
    confidence_threshold = 0.3  # Lowered from 0.7 to catch more colors
    
    # Track in which frames each color appears
    hex_colors = defaultdict(set)
    w3c_colors = defaultdict(set)
    
    for frame in response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        
        # Access color concepts from the frame data
        for concept in frame.data.concepts:
            if concept.value >= confidence_threshold:
                name = concept.name.lower()
                # Check if it's a hex color (starts with #)
                if name.startswith('#'):
                    hex_colors[name].add(timestamp)
                else:
                    w3c_colors[name].add(timestamp)

    # Calculate distribution percentages
    hex_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in hex_colors.items()
    }

    w3c_distribution = {
        name: round((len(frames) / total_frames) * 100, 2)
        for name, frames in w3c_colors.items()
    }

    # Sort by percentage for clearer output
    sorted_hex = dict(sorted(hex_distribution.items(), key=lambda x: x[1], reverse=True))
    sorted_w3c = dict(sorted(w3c_distribution.items(), key=lambda x: x[1], reverse=True))

    return {
        "total_frames_analyzed": total_frames,
        "unique_colors_detected": {
            "hex": len(hex_colors),
            "w3c": len(w3c_colors)
        },
        "color_distribution_percent": {
            "hex": sorted_hex,
            "w3c": sorted_w3c
        }
    } 
