# IFC Answer Engine API Documentation

## Overview

The IFC Answer Engine API is a FastAPI-based web service that provides intelligent question-answering capabilities for Building Information Modeling (BIM) models in Industry Foundation Classes (IFC) format. The API uses advanced AI agents to interpret natural language questions and extract relevant information from IFC files.

**Base URL:** `http://localhost:8000`

## 🚀 Quick Start

### Prerequisites

- Python 3.12
- Project dependencies installed (see [Installation](#installation))
- MLflow tracking server (optional but recommended)

### Installation

```bash
# Clone the repository and navigate to the project root
cd cobbie

# Install dependencies
pip install -e .

# Or using uv (recommended)
uv sync
```

### Starting the Server

```bash
# Option 1: Using the startup script (recommended)
python api/start_server.py

# Option 2: Direct execution
python api/main.py

# Option 3: Using uvicorn
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

The server will be available at:
- **API Base**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/redoc

## 📡 API Endpoints

### Health Check

#### `GET /`

**Purpose**: Check if the API server is running and responsive.

**URL**: `http://localhost:8000/`

**Headers**: None required

**Request Body**: None

**Response Format**: JSON

**Response Schema**:
```typescript
interface HealthCheckResponse {
  message: string;
}
```

**Response Example**:
```json
{
  "message": "IFC Answer Engine API is running"
}
```

**HTTP Status Codes**:
- `200 OK`: Server is running normally

**Frontend Integration Notes**:
- Use this endpoint for health checks and connectivity testing
- No authentication required
- Suitable for periodic health monitoring
- Fast response time (< 100ms typically)

---

### Question Answering

#### `POST /ask`

**Purpose**: Submit a natural language question about a specific BIM model and receive an AI-generated answer.

**URL**: `http://localhost:8000/ask`

**Method**: POST

**Content-Type**: `application/json`

**Headers**:
```
Content-Type: application/json
```

**Request Body Schema**:
```typescript
interface QuestionRequest {
  question: string;    // Required: Natural language question (1-1000 characters)
  model_id: number;    // Required: Positive integer ID of the BIM model
}
```

**Request Validation Rules**:
- `question`: Non-empty string, max 1000 characters
- `model_id`: Positive integer (> 0)

**Request Examples**:
```json
// Geometric query
{
  "question": "What is the total floor area of the building?",
  "model_id": 1
}

// Element counting
{
  "question": "How many doors are in the first floor?",
  "model_id": 2
}

// Material information
{
  "question": "What materials are used in the external walls?",
  "model_id": 1
}

// Spatial relationships
{
  "question": "Which rooms are connected to the kitchen?",
  "model_id": 3
}
```

**Response Schema**:
```typescript
interface QuestionResponse {
  status: 'success' | 'error';
  answer: string | null;          // Present when status is 'success'
  error_msg: string | null;       // Present when status is 'error'
  model_info: ModelInfo | null;   // Present when status is 'success'
}

interface ModelInfo {
  id: number;
  project_name: string;
  model_name: string;
  model_description: string;
}
```

**Success Response Example**:
```json
{
  "status": "success",
  "answer": "The total floor area of the building is 125.5 square meters, distributed across two floors: Ground floor (65.2 sq m) and First floor (60.3 sq m).",
  "error_msg": null,
  "model_info": {
    "id": 1,
    "project_name": "duplex",
    "model_name": "arc",
    "model_description": "Architectural model of a duplex"
  }
}
```

**Error Response Examples**:
```json
// Model not found
{
  "status": "error",
  "answer": null,
  "error_msg": "BIM model with ID 999 not found",
  "model_info": null
}

// Processing error
{
  "status": "error",
  "answer": null,
  "error_msg": "Unable to process question: IFC file is corrupted",
  "model_info": null
}
```

**HTTP Status Codes**:
- `200 OK`: Request processed (check `status` field for actual result)
- `404 Not Found`: Model with specified ID not found
- `422 Unprocessable Entity`: Invalid request format or validation error
- `500 Internal Server Error`: Unexpected server error

**Processing Time**: 5-30 seconds (varies by question complexity and model size)

**Frontend Integration Notes**:
- Always check the `status` field in the response
- Display loading state during processing (can take 10-30 seconds)
- Handle both success and error cases appropriately
- The `answer` field contains the final user-facing response
- `model_info` provides context about which model was queried

---

### Model Management

#### `GET /models`

**Purpose**: Retrieve a complete list of all available BIM models in the system.

**URL**: `http://localhost:8000/models`

**Method**: GET

**Headers**: None required

**Request Body**: None

**Response Schema**:
```typescript
interface ModelsResponse {
  models: BIMModel[];
}

interface BIMModel {
  id: number;                    // Unique model identifier
  project_name: string;          // Project/building name
  model_name: string;            // Model type (e.g., "arc", "structural", "mep")
  model_description: string;     // Human-readable description
  model_path: string;           // Server-side file path (for reference)
  supabase_url: string;         // Public URL for model viewing/download
}
```

**Response Example**:
```json
{
  "models": [
    {
      "id": 1,
      "project_name": "duplex",
      "model_name": "arc",
      "model_description": "Architectural model of a duplex",
      "model_path": "/app/models/duplex_arc.ifc",
      "supabase_url": "https://wzutfspshgtxjvquwdla.supabase.co/storage/v1/object/public/ifc_models/1.ifc"
    },
    {
      "id": 2,
      "project_name": "office_building",
      "model_name": "structural",
      "model_description": "Structural model of office building",
      "model_path": "/app/models/office_structural.ifc",
      "supabase_url": "https://wzutfspshgtxjvquwdla.supabase.co/storage/v1/object/public/ifc_models/2.ifc"
    },
    {
      "id": 3,
      "project_name": "warehouse",
      "model_name": "mep",
      "model_description": "MEP (Mechanical, Electrical, Plumbing) model",
      "model_path": "/app/models/warehouse_mep.ifc",
      "supabase_url": "https://wzutfspshgtxjvquwdla.supabase.co/storage/v1/object/public/ifc_models/3.ifc"
    }
  ]
}
```

**Empty Response Example**:
```json
{
  "models": []
}
```

**HTTP Status Codes**:
- `200 OK`: Models retrieved successfully (may be empty array)
- `500 Internal Server Error`: Database connection error or server error

**Response Time**: < 1 second typically

**Frontend Integration Notes**:
- Use for populating model selection dropdowns/lists
- Display `project_name` and `model_description` to users
- Use `id` for subsequent API calls
- `supabase_url` can be used for model visualization in 3D viewers
- Cache this data locally to avoid repeated requests
- Handle empty arrays gracefully (show "No models available" message)

---

### File Download

#### `GET /models/{model_id}/ifc`

**Purpose**: Download the raw IFC file for a specific model.

**URL**: `http://localhost:8000/models/{model_id}/ifc`

**Method**: GET

**Path Parameters**:
- `model_id` (integer): The unique ID of the model to download

**Headers**: None required

**Request Body**: None

**URL Examples**:
```
http://localhost:8000/models/1/ifc
http://localhost:8000/models/2/ifc
http://localhost:8000/models/999/ifc  // Will return 404
```

**Response Format**: Binary file (IFC format)

**Response Headers**:
```
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="{project_name}_{model_name}_{model_id}.ifc"
Content-Length: {file_size_in_bytes}
```

**Filename Pattern**: `{project_name}_{model_name}_{model_id}.ifc`

**Example Filenames**:
- `duplex_arc_1.ifc`
- `office_building_structural_2.ifc`
- `warehouse_mep_3.ifc`

**HTTP Status Codes**:
- `200 OK`: File download successful
- `404 Not Found`: Model with specified ID doesn't exist
- `404 Not Found`: Model exists but file not found on server
- `500 Internal Server Error`: File system error or server error

**File Size Range**: 100KB - 50MB typically

**Frontend Integration Notes**:
- Use for downloading models for offline analysis
- Handle large file downloads with progress indicators
- Implement proper error handling for failed downloads
- Consider using the filename from `Content-Disposition` header
- For 3D visualization, consider using the `supabase_url` from `/models` instead

## 🔧 Configuration

### Environment Variables

The API uses the following configuration:

```bash
# MLflow tracking (optional)
MLFLOW_URI=http://localhost:5000  # Set in src/config/__init__.py

# CORS settings (currently allows all origins - configure for production)
CORS_ORIGINS=*
```

### CORS Configuration

The API is configured with permissive CORS settings for development:

```python
allow_origins=["*"]      # Configure specific domains in production
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

## 📊 Monitoring & Tracking

### MLflow Integration

The API automatically tracks all interactions using MLflow:

- **Experiment Name**: "API"
- **Tracked Data**:
  - Request inputs (question, model_id, timestamp)
  - Response outputs (status, answer, duration)
  - Model information and error details
  - Performance metrics

**Viewing Traces:**
1. Start MLflow server: `mlflow ui`
2. Navigate to http://localhost:5000
3. Select the "API" experiment
4. View detailed traces for each API call

### Span Information

Each API call creates a detailed span with:
- Input parameters
- Model metadata
- Execution duration
- Success/error status
- Exception details (if any)

## 🔗 Frontend Integration Guide

### TypeScript Interfaces

Complete TypeScript definitions for all API responses:

```typescript
// API Base URL
export const API_BASE_URL = 'http://localhost:8000';

// Health Check
export interface HealthCheckResponse {
  message: string;
}

// Models Endpoint
export interface BIMModel {
  id: number;
  project_name: string;
  model_name: string;
  model_description: string;
  model_path: string;
  supabase_url: string;
}

export interface ModelsResponse {
  models: BIMModel[];
}

// Question Endpoint
export interface QuestionRequest {
  question: string;
  model_id: number;
}

export interface ModelInfo {
  id: number;
  project_name: string;
  model_name: string;
  model_description: string;
}

export interface QuestionResponse {
  status: 'success' | 'error';
  answer: string | null;
  error_msg: string | null;
  model_info: ModelInfo | null;
}

// API Error Types
export interface APIError {
  detail: string;
  status_code: number;
}
```

### Frontend Service Class

Complete service implementation for frontend integration:

```typescript
export class IFCAnswerEngineAPI {
  private baseURL: string;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
  }

  // Health check with error handling
  async checkHealth(): Promise<HealthCheckResponse> {
    try {
      const response = await fetch(`${this.baseURL}/`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Health check failed:', error);
      throw new Error('API server is not reachable');
    }
  }

  // Get all models with caching support
  async getModels(): Promise<BIMModel[]> {
    try {
      const response = await fetch(`${this.baseURL}/models`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: ModelsResponse = await response.json();
      return data.models;
    } catch (error) {
      console.error('Failed to fetch models:', error);
      throw new Error('Unable to load BIM models');
    }
  }

  // Ask question with comprehensive error handling
  async askQuestion(question: string, modelId: number): Promise<QuestionResponse> {
    // Input validation
    if (!question.trim()) {
      throw new Error('Question cannot be empty');
    }

    if (modelId <= 0) {
      throw new Error('Model ID must be a positive integer');
    }

    if (question.length > 1000) {
      throw new Error('Question is too long (maximum 1000 characters)');
    }

    const requestBody: QuestionRequest = {
      question: question.trim(),
      model_id: modelId
    };

    try {
      const response = await fetch(`${this.baseURL}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        // Handle different HTTP status codes
        if (response.status === 404) {
          throw new Error(`Model with ID ${modelId} not found`);
        } else if (response.status === 422) {
          const errorData = await response.json();
          throw new Error(`Invalid request: ${errorData.detail}`);
        } else if (response.status >= 500) {
          throw new Error('Server error - please try again later');
        } else {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
      }

      const result: QuestionResponse = await response.json();
      return result;
    } catch (error) {
      console.error('Question API call failed:', error);
      throw error;
    }
  }

  // Download IFC file with progress tracking
  async downloadIFCFile(modelId: number, onProgress?: (progress: number) => void): Promise<Blob> {
    try {
      const response = await fetch(`${this.baseURL}/models/${modelId}/ifc`);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(`Model with ID ${modelId} not found or file unavailable`);
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Get file size for progress tracking
      const contentLength = response.headers.get('Content-Length');
      const total = contentLength ? parseInt(contentLength, 10) : 0;

      if (!response.body) {
        throw new Error('Response body is empty');
      }

      const reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let loaded = 0;

      while (true) {
        const { done, value } = await reader.read();

        if (done) break;

        chunks.push(value);
        loaded += value.length;

        if (onProgress && total > 0) {
          onProgress((loaded / total) * 100);
        }
      }

      // Combine chunks into final blob
      const allChunks = new Uint8Array(loaded);
      let position = 0;
      for (const chunk of chunks) {
        allChunks.set(chunk, position);
        position += chunk.length;
      }

      return new Blob([allChunks], { type: 'application/octet-stream' });
    } catch (error) {
      console.error('File download failed:', error);
      throw error;
    }
  }

  // Get filename from response headers
  extractFilename(response: Response): string {
    const contentDisposition = response.headers.get('Content-Disposition');
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/);
      if (match) {
        return match[1];
      }
    }
    return 'model.ifc'; // fallback filename
  }
}
```

### React Hooks for State Management

```typescript
import { useState, useEffect, useCallback } from 'react';

// Hook for managing models
export function useModels() {
  const [models, setModels] = useState<BIMModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const api = new IFCAnswerEngineAPI();

  const fetchModels = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const modelList = await api.getModels();
      setModels(modelList);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  return { models, loading, error, refetch: fetchModels };
}

// Hook for asking questions
export function useQuestionSubmission() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<QuestionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const api = new IFCAnswerEngineAPI();

  const submitQuestion = useCallback(async (question: string, modelId: number) => {
    try {
      setIsSubmitting(true);
      setError(null);
      setResult(null);

      const response = await api.askQuestion(question, modelId);
      setResult(response);

      // Additional validation for business logic
      if (response.status === 'error') {
        setError(response.error_msg || 'Unknown error occurred');
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to submit question';
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  }, []);

  const clearResults = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return {
    submitQuestion,
    isSubmitting,
    result,
    error,
    clearResults
  };
}

// Hook for file downloads
export function useFileDownload() {
  const [isDownloading, setIsDownloading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const api = new IFCAnswerEngineAPI();

  const downloadFile = useCallback(async (modelId: number, filename?: string) => {
    try {
      setIsDownloading(true);
      setError(null);
      setProgress(0);

      const blob = await api.downloadIFCFile(modelId, setProgress);

      // Trigger download
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `model_${modelId}.ifc`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      setProgress(100);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Download failed';
      setError(errorMessage);
    } finally {
      setIsDownloading(false);
    }
  }, []);

  return {
    downloadFile,
    isDownloading,
    progress,
    error
  };
}
```

### Error Handling Patterns

```typescript
// Centralized error handling
export class APIErrorHandler {
  static handleAPIError(error: unknown): string {
    if (error instanceof Error) {
      // Network errors
      if (error.message.includes('fetch')) {
        return 'Network connection failed. Please check your internet connection.';
      }

      // Timeout errors
      if (error.message.includes('timeout')) {
        return 'Request timed out. The server may be busy, please try again.';
      }

      // Validation errors
      if (error.message.includes('validation')) {
        return 'Invalid input data. Please check your request and try again.';
      }

      return error.message;
    }

    return 'An unexpected error occurred. Please try again.';
  }

  static isRetryableError(error: unknown): boolean {
    if (error instanceof Error) {
      // Retry on network errors and server errors
      return error.message.includes('Network') ||
             error.message.includes('Server error') ||
             error.message.includes('timeout');
    }
    return false;
  }
}

// Retry mechanism
export async function withRetry<T>(
  operation: () => Promise<T>,
  maxRetries: number = 3,
  delay: number = 1000
): Promise<T> {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await operation();
    } catch (error) {
      if (attempt === maxRetries || !APIErrorHandler.isRetryableError(error)) {
        throw error;
      }

      // Exponential backoff
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, attempt - 1)));
    }
  }

  throw new Error('Max retries exceeded');
}
```

### Usage Examples for Frontend Components

```typescript
// Example: Model Selection Component
export function ModelSelector() {
  const { models, loading, error } = useModels();
  const [selectedModel, setSelectedModel] = useState<number | null>(null);

  if (loading) return <div>Loading models...</div>;
  if (error) return <div>Error: {error}</div>;
  if (models.length === 0) return <div>No models available</div>;

  return (
    <select onChange={(e) => setSelectedModel(Number(e.target.value))}>
      <option value="">Select a model</option>
      {models.map(model => (
        <option key={model.id} value={model.id}>
          {model.project_name} - {model.model_description}
        </option>
      ))}
    </select>
  );
}

// Example: Question Form Component
export function QuestionForm() {
  const [question, setQuestion] = useState('');
  const [modelId, setModelId] = useState<number | null>(null);
  const { submitQuestion, isSubmitting, result, error } = useQuestionSubmission();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (question.trim() && modelId) {
      await submitQuestion(question, modelId);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask a question about the BIM model..."
        maxLength={1000}
        disabled={isSubmitting}
      />
      <button type="submit" disabled={isSubmitting || !question.trim() || !modelId}>
        {isSubmitting ? 'Processing...' : 'Ask Question'}
      </button>

      {error && <div className="error">{error}</div>}
      {result && result.status === 'success' && (
        <div className="answer">
          <h3>Answer:</h3>
          <p>{result.answer}</p>
          <small>Model: {result.model_info?.project_name}</small>
        </div>
      )}
    </form>
  );
}
```

### cURL Examples

```bash
# Health check
curl -X GET "http://localhost:8000/"

# List models
curl -X GET "http://localhost:8000/models"

# Ask a question
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What materials are used in the walls?",
    "model_id": 1
  }'

# Download model file
curl -O -J "http://localhost:8000/models/1/ifc"
```

## 🎯 Question Types & Capabilities

The API can handle various types of questions about BIM models:

### Geometric Queries
- "What is the height of the building?"
- "What are the dimensions of the living room?"
- "How much floor area does the kitchen have?"

### Element Counting
- "How many doors are in the building?"
- "Count the number of windows on the first floor"
- "How many rooms are there?"

### Material Information
- "What materials are used in the foundation?"
- "List all the materials used in this model"
- "What type of insulation is used?"

### Spatial Relationships
- "Which rooms are connected to the kitchen?"
- "What spaces are on the second floor?"
- "Find all rooms with external walls"

### Property Queries
- "What are the fire rating properties of the doors?"
- "Get the thermal properties of the walls"
- "What is the load-bearing capacity of the beams?"

## ⚠️ Error Handling

### Common Error Scenarios

| Error Code | Scenario | Response |
|------------|----------|----------|
| 404 | Model not found | `{"status": "error", "error_msg": "BIM model with ID X not found"}` |
| 404 | Model file missing | `{"status": "error", "error_msg": "BIM model file not found at path: ..."}` |
| 422 | Invalid request | Validation error details |
| 500 | Server error | `{"status": "error", "error_msg": "An unexpected error occurred: ..."}` |

### Error Response Format

All error responses follow a consistent format:

```json
{
  "status": "error",
  "answer": null,
  "error_msg": "Detailed error description",
  "model_info": null
}
```

## 🚀 Deployment

### Development

```bash
# Start with auto-reload
python api/start_server.py
```

### Production

```bash
# Using gunicorn (install with: pip install gunicorn)
gunicorn api.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Using uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker (Optional)

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -e .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 🔍 Troubleshooting

### Common Issues

1. **Server won't start**
   - Check Python version (requires 3.12)
   - Verify all dependencies are installed
   - Ensure port 8000 is not in use

2. **Model not found errors**
   - Check database connection
   - Verify model files exist at specified paths
   - Check model ID validity

3. **MLflow connection issues**
   - MLflow server must be running
   - Check MLFLOW_URI configuration
   - Verify network connectivity

4. **CORS issues**
   - Configure allowed origins for production
   - Check browser console for CORS errors

### Debug Mode

Enable debug logging by setting the log level in the engine configuration:

```python
# In your startup script
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Performance Considerations

- **Cold Start**: First request may take longer as models load
- **Concurrent Requests**: API handles concurrent requests efficiently
- **Large Models**: Processing time varies with IFC file size and complexity
- **MLflow Overhead**: Disable tracking in production if performance is critical

## 🔗 Related Documentation

- [Engine API Documentation](api.md) - Core engine classes and methods
- [Project README](../README.md) - Project overview and setup
- [Frontend Documentation](../frontend/README.md) - Web interface documentation

## 📝 License

This project is part of the IFC Answer Engine V3 system. Please refer to the main project documentation for licensing information.

---

**Last Updated**: December 2024
**API Version**: 1.0.0
**FastAPI Version**: 0.115.9+
