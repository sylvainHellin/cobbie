# IFC Answer Engine API

A FastAPI-based web service for answering questions about BIM models in IFC format.

## Features

- **Question Answering**: Ask natural language questions about BIM models
- **Model Management**: List and query available BIM models
- **Error Handling**: Comprehensive error handling with meaningful messages
- **CORS Support**: Cross-origin requests enabled for web applications
- **MLflow Tracing**: Full tracing of API interactions with MLflow for monitoring and analytics

## API Endpoints

### POST `/ask`

Ask a question about a specific BIM model.

**Request Body:**
```json
{
  "question": "What is the height of the living room?",
  "model_id": 1
}
```

**Response:**
```json
{
  "status": "success",
  "answer": "The height of the living room is 2.7 meters.",
  "error_msg": null,
  "model_info": {
    "id": 1,
    "project_name": "duplex",
    "model_name": "arc",
    "model_description": "Architectural model of a duplex"
  }
}
```

### GET `/models`

Get a list of all available BIM models.

**Response:**
```json
{
  "models": [
    {
      "id": 1,
      "project_name": "duplex",
      "model_name": "arc",
      "model_description": "Architectural model of a duplex",
      "model_path": "/path/to/model.ifc"
    }
  ]
}
```

### GET `/models/{model_id}/ifc`

Download the IFC file for a specific model.

**Parameters:**
- `model_id` (path parameter): The ID of the model to download

**Response:**
Returns the IFC file as a binary download with appropriate headers for file download.

**Example:**
```bash
curl -O http://127.0.0.1:8000/models/1/ifc
# Downloads the IFC file for model with ID 1
```

The downloaded file will be named using the pattern: `{project_name}_{model_name}_{model_id}.ifc`

**Error Responses:**
- `404 Not Found`: Model with the specified ID doesn't exist
- `404 Not Found`: Model file not found at the stored path
- `500 Internal Server Error`: Unexpected server error

### GET `/`

Health check endpoint.

## Running the API

There are several ways to run the API server:

### Option 1: Using the startup script (Recommended)
```bash
uv run python api/start_server.py
```

### Option 2: Using uvicorn directly
```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

### Option 3: From the api directory
```bash
cd api
uv run python main.py
```

The API will be available at `http://127.0.0.1:8000`

**Note**: Make sure you have the project dependencies installed using `uv`. All Python commands should use the `uv run` prefix to ensure proper dependency management.

## MLflow Tracking

The API automatically tracks all interactions with MLflow:

- **Experiment**: All API calls are logged under the "API" experiment
- **Spans**: Each API endpoint creates a span with detailed input/output logging
- **Metrics**: Duration, status, and error information are tracked
- **Attributes**: Model information and request details are recorded

To view the MLflow tracking:
1. Make sure MLflow server is running (usually at `http://127.0.0.1:5000`)
2. Navigate to the MLflow UI to see the "API" experiment
3. View detailed traces and metrics for each API call

## Interactive Documentation

Once the server is running, you can access:
- **Swagger UI**: `http://127.0.0.1:8000/docs`
- **ReDoc**: `http://127.0.0.1:8000/redoc`

## Example Usage with curl

```bash
# List available models
curl -X GET "http://127.0.0.1:8000/models"

# Ask a question about a model
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "How many rooms are in this building?",
    "model_id": 1
  }'
```

## Example Usage with Python

```python
import requests

# Base URL for the API
BASE_URL = "http://127.0.0.1:8000"

# List available models
response = requests.get(f"{BASE_URL}/models")
models = response.json()["models"]
print(f"Available models: {len(models)}")

# Ask a question
question_data = {
    "question": "What is the total floor area?",
    "model_id": 1
}

response = requests.post(f"{BASE_URL}/ask", json=question_data)
result = response.json()

if result["status"] == "success":
    print(f"Answer: {result['answer']}")
else:
    print(f"Error: {result['error_msg']}")
```

## Error Handling

The API provides detailed error messages for common scenarios:

- **404**: Model not found or model file doesn't exist
- **422**: Invalid request format or missing required fields
- **500**: Internal server errors with detailed error messages

All error responses follow the same format:
```json
{
  "status": "error",
  "answer": null,
  "error_msg": "Detailed error description",
  "model_info": null
}
```