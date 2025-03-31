from collections import Counter
from typing import Dict, Any
from clarifai_grpc.grpc.api import service_pb2

def analyze_colors(response: service_pb2.MultiOutputResponse) -> Dict[str, Any]:
    """Analyzes color recognition results for dominant colors."""
    if not response or not response.outputs:
        return {"error": "No response data"}

    dominant_color_counts = Counter()
    total_frames = len(response.outputs[0].data.frames)
    # Clarifai color model often returns hex codes AND w3c names. We'll prefer names.

    for frame in response.outputs[0].data.frames:
        # Find the concept with the highest value (dominant color for the frame)
        dominant_frame_color = None
        max_value = 0
        for concept in frame.data.concepts:
            if concept.value > max_value:
                max_value = concept.value
                # Prefer the W3C name if available
                dominant_frame_color = concept.name

        if dominant_frame_color:
            dominant_color_counts[dominant_frame_color] += 1

    # Calculate frequency distribution
    dominant_color_frequency = {
        name: round((count / total_frames) * 100, 2)
        for name, count in dominant_color_counts.items()
    }

    # Get top N dominant colors overall
    top_n = 5
    top_dominant_colors = dominant_color_counts.most_common(top_n)

    return {
        "total_frames_analyzed": total_frames,
        "top_dominant_colors_overall": dict(top_dominant_colors), # Top N colors and frame counts
        "dominant_color_frequency_percent": dominant_color_frequency # Percentage of frames each color was dominant
    } 
