from collections import Counter, defaultdict
from typing import Dict, Any, Optional
from clarifai_grpc.grpc.api import service_pb2

def analyze_faces(face_responses: Dict[str, service_pb2.MultiOutputResponse]) -> Dict[str, Any]:
    """Analyzes results from various face models (detection, demographics, sentiment)."""
    if not face_responses:
        return {"error": "No face model responses provided"}

    # Extract primary face detection results if available
    detection_response = face_responses.get("face_detection")
    if not detection_response or not detection_response.outputs:
        return {"no_faces_detected": True, "reason": "Face detection model did not return results"}

    total_detection_frames = len(detection_response.outputs[0].data.frames)
    frame_face_counts = []
    total_faces_detected = 0

    # --- Aggregate results frame by frame --- 
    # This is complex because regions in one model's output (e.g., detection)
    # need to be correlated with concepts from another model's output (e.g., age)
    # applied to the same frame. Clarifai Workflows are better suited for this.
    # For a simplified approach here, we'll aggregate stats per model type across all frames.

    sentiment_counts = Counter()
    age_counts = Counter()
    gender_counts = Counter()
    multiculturality_counts = Counter()

    # Process Detection Frames for Counts
    for frame in detection_response.outputs[0].data.frames:
        timestamp = frame.frame_info.time
        num_faces_in_frame = len(frame.data.regions) # Regions are faces in detection model
        frame_face_counts.append((timestamp, num_faces_in_frame))
        total_faces_detected += num_faces_in_frame

    # Helper function to process concept-based face models (age, gender, etc.)
    def process_concept_model(model_name, counter):
        response = face_responses.get(model_name)
        if response and response.outputs:
            for frame in response.outputs[0].data.frames:
                 # These models might return concepts directly on the frame or within regions.
                 # Assuming direct concepts for simplicity - check actual model output structure.
                 # A more robust approach matches regions if possible.
                 for concept in frame.data.concepts:
                      # You might add a confidence threshold here too
                      counter[concept.name.lower()] += 1
            return True
        return False

    # Process other face models if their responses exist
    process_concept_model("face_sentiment", sentiment_counts)
    process_concept_model("face_age", age_counts)
    process_concept_model("face_gender", gender_counts)
    process_concept_model("face_multiculturality", multiculturality_counts)

    # Calculate distributions (as percentage of total frames where the model ran)
    # Note: This is approximate if models didn't run/succeed on all frames.
    # A better denominator would be frames where *that specific model* returned results.
    def calculate_distribution(counter):
         total = sum(counter.values())
         if total == 0: return {}
         return {k: round((v / total) * 100, 2) for k, v in counter.items()}


    return {
        "total_frames_analyzed_by_detection": total_detection_frames,
        "total_faces_detected_across_frames": total_faces_detected,
        "avg_faces_per_frame": round(total_faces_detected / total_detection_frames, 2) if total_detection_frames else 0,
        "frame_by_frame_face_count": frame_face_counts,
        "sentiment_distribution_percent": calculate_distribution(sentiment_counts),
        "age_distribution_percent": calculate_distribution(age_counts),
        "gender_distribution_percent": calculate_distribution(gender_counts),
        "multiculturality_distribution_percent": calculate_distribution(multiculturality_counts),
        # TODO: Add tracking of faces across frames (requires embeddings/tracking model)
    } 
