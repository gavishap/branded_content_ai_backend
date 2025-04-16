
# Branded Content AI - Backend

## Overview

This is the backend API for Branded Content AI, a video analysis platform that leverages multiple AI models to provide comprehensive insights for marketing videos. The system combines Google Gemini and ClarifAI analyses to offer a unified understanding of video content.

## Features

- Video analysis using multiple AI models
- Demographic analysis and representation metrics
- Emotional content analysis
- Performance prediction metrics
- Content quality assessment
- Unified analysis combining multiple AI perspectives

## Installation

### Prerequisites

- Python 3.8+
- AWS account with S3 access
- Google Gemini API key
- ClarifAI API key

### Setup

1. Clone the repository
```bash
git clone [your-repo-url]
cd branded_content_ai/backend
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your API keys
```
GOOGLE_GEMINI_API_KEY=your_gemini_api_key
CLARIFAI_API_KEY=your_clarifai_api_key
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
S3_BUCKET_NAME=your_s3_bucket_name
```

## Running the Server

```bash
python main.py
```

The server will start on `http://localhost:5000`.

## API Endpoints

### `/api/analyze-unified`

Analyzes a video using both Gemini and ClarifAI models and produces a unified analysis.

**Method**: POST

**Request Body**:
- Form data with video file OR
- JSON with `url` field for video URL

**Response**:
- `analysis_id`: UUID of the analysis
- `status`: "processing"

### `/api/analysis-progress/{id}`

Gets the progress of an ongoing analysis.

**Method**: GET

**Response**:
- `analysis_id`: ID of the analysis
- `progress`: Percentage completion (0-100)
- `step`: Current processing step
- `status`: Current status
- `result`: Complete analysis (when finished)

### `/api/analysis/{analysis_id}`

Retrieves a completed analysis.

**Method**: GET

**Response**: Full analysis JSON

### `/api/saved-analyses`

Lists all saved analyses.

**Method**: GET

**Response**: List of analysis metadata

## Analysis Pipeline

1. **Video Ingestion**: Process video from upload or URL
2. **Parallel Analysis**:
   - Gemini analyzes content, style, performance metrics
   - ClarifAI analyzes visual elements, demographics, emotions
3. **Unification**: Combines analyses with weighted reconciliation
4. **Validation**: Ensures data consistency and completeness
5. **Storage**: Saves results to S3 and returns to client

## Project Structure

- `main.py`: Flask application entry point
- `narrative_analyzer.py`: Handles Gemini analysis
- `clarif_ai_insights.py`: Handles ClarifAI analysis
- `unified_analysis.py`: Combines AI insights
- `api_routes.py`: API endpoint definitions
- `s3_utils.py`: AWS S3 interaction utilities

## Development

### Adding New Analysis Features

To add new analysis capabilities:

1. Update the prompt in `narrative_analyzer.py` for Gemini features
2. Modify `clarif_ai_insights.py` for ClarifAI features
3. Update `unified_analysis.py` JSON structure to include new fields
4. Ensure frontend compatibility by updating output structures

### Debugging

- Analyze output is saved to `unified_analyses/` directory
- Raw responses from models are saved to `raw_gemini_response_*.txt`
- Use the `/api/analysis-progress/{id}` endpoint to monitor processing

## Deployment

The backend is designed to be deployed as a containerized service:

```bash
docker build -t branded-content-ai-backend .
docker run -p 5000:5000 branded-content-ai-backend
```

## Contributing

1. Create a feature branch: `git checkout -b feature/new-feature`
2. Make changes
3. Run tests: `pytest`
4. Submit a pull request

## License

[Your license here]
