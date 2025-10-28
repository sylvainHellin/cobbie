"""FastAPI application for the IFC Answer Engine."""

import os
import traceback
from datetime import datetime
from functools import partial

import mlflow
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from api.models import QuestionRequest, QuestionResponse
from src.config import LLM, MLFLOW_URI
from src.engine import create_engine

# from src.experiment.db.query_db import get_ifc_models
from src.experiment.db.query import get_ifc_model, get_ifc_models

app = FastAPI(
    title="IFC Answer Engine API",
    description="API for answering questions about BIM models in IFC format",
    version="1.0.0",
)

# Add CORS middleware to allow requests from web browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure MLflow for API tracking
mlflow.set_tracking_uri(MLFLOW_URI)
mlflow.set_experiment("API")
mlflow.dspy.autolog()  # type: ignore

# Initialize the IFC Answer Engine with configurable type
# Engine type can be set via ENGINE_TYPE environment variable ("dspy" or "baml")
# Default is "dspy" for backward compatibility
engine_type = os.getenv("ENGINE_TYPE", "baml").lower()

if engine_type not in ["dspy", "baml"]:
    raise ValueError(f"Invalid ENGINE_TYPE: {engine_type}. Must be 'dspy' or 'baml'")

print(f"🚀 Starting API with {engine_type.upper()} engine")

# Optional LLM override for DSPy engine
llm = None
if engine_type == "dspy":
    # Uncomment and configure if you want to use a specific LLM for DSPy
    # llm = LLM(model_name="qwen-3-coder-480b", provider_name="cerebras").get_llm()
    pass

# Create engine using factory function
engine = create_engine(engine_type=engine_type, llm=llm)


@app.get("/")
async def root():
    """Root endpoint to check if the API is running."""
    return {"message": "IFC Answer Engine API is running"}


@app.post("/ask", response_model=QuestionResponse)
async def ask_question(request: QuestionRequest) -> QuestionResponse:
    """
    Ask a question about a BIM model.

    Args:
        request: The question request containing the question and model ID

    Returns:
        QuestionResponse: The answer along with status and any error information
    """
    start_time = datetime.now()

    # Set the experiment and start an MLflow run to properly capture traces
    mlflow.set_experiment("API")
    run_name = f"API_Question_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        # Create a nested run for the engine execution (this is where traces will be stored)
        engine_run_name = f"Engine_{request.model_id}_{datetime.now().strftime('%H%M%S')}"
        with mlflow.start_run(run_name=engine_run_name, nested=True) as engine_run:
            with mlflow.start_span(name="API_ask_question", span_type="API") as span:
                # Log the inputs
                span.set_inputs(
                    {
                        "question": request.question,
                        "model_id": request.model_id,
                        "timestamp": start_time.isoformat(),
                    }
                )

                try:
                    # Get the IFC model information from the database (run in threadpool)
                    ifc_model = get_ifc_model(id=request.model_id)

                    if not ifc_model:
                        error_msg = f"BIM model with ID {request.model_id} not found"
                        span.set_outputs(
                            {
                                "status": "error",
                                "error_msg": error_msg,
                                "duration_seconds": (
                                    datetime.now() - start_time
                                ).total_seconds(),
                            }
                        )
                        raise HTTPException(status_code=404, detail=error_msg)

                    if not ifc_model.model_path or not os.path.exists(ifc_model.model_path):
                        error_msg = f"BIM model file not found at path: {ifc_model.model_path}"
                        span.set_outputs(
                            {
                                "status": "error",
                                "error_msg": error_msg,
                                "duration_seconds": (
                                    datetime.now() - start_time
                                ).total_seconds(),
                            }
                        )
                        raise HTTPException(status_code=404, detail=error_msg)

                    # Log model information
                    span.set_attributes(
                        {
                            "model_path": ifc_model.model_path,
                            "project_name": ifc_model.project_name,
                            "model_name": ifc_model.model_name,
                        }
                    )

                    # Use the engine to answer the question (run in threadpool)
                    result = await run_in_threadpool(
                        partial(
                            engine.forward,
                            question=request.question,
                            path_ifc_model=ifc_model.model_path,
                        )
                    )

                    # Prepare model information
                    model_info = {
                        "id": ifc_model.id,
                        "project_name": ifc_model.project_name,
                        "model_name": ifc_model.model_name,
                        "model_description": ifc_model.model_description,
                    }

                    duration = (datetime.now() - start_time).total_seconds()

                    # Log the outputs
                    span.set_outputs(
                        {
                            "status": result.status,
                            "answer": result.result.answer,
                            "error_msg": result.error_msg,
                            "duration_seconds": duration,
                            "model_info": model_info,
                        }
                    )

                    return QuestionResponse(
                        status=result.status,
                        answer=result.result.answer,
                        error_msg=result.error_msg,
                        model_info=model_info,
                    )

                except HTTPException:
                    # Re-raise HTTP exceptions
                    raise
                except Exception as e:
                    # Handle any other unexpected errors
                    error_msg = f"An unexpected error occurred: {str(e)}"
                    duration = (datetime.now() - start_time).total_seconds()

                    span.set_outputs(
                        {
                            "status": "error",
                            "error_msg": error_msg,
                            "duration_seconds": duration,
                            "exception": str(e),
                        }
                    )

                    print(f"Error in ask_question: {error_msg}")
                    print(f"Traceback: {traceback.format_exc()}")

                    return QuestionResponse(
                        status="error", answer=None, error_msg=error_msg, model_info=None
                    )


@app.get("/models")
async def list_models():
    """
    Get a list of all available BIM models.

    Returns:
        List of available BIM models with their information
    """
    start_time = datetime.now()

    with mlflow.start_span(name="API_list_models", span_type="API") as span:
        # Log the inputs
        span.set_inputs({"timestamp": start_time.isoformat()})

        try:
            # Query models from DB in threadpool
            ifc_models = await run_in_threadpool(get_ifc_models)

            models = []
            for model in ifc_models:
                models.append(
                    {
                        "id": model.id,
                        "project_name": model.project_name,
                        "model_name": model.model_name,
                        "model_description": model.model_description,
                        "model_path": model.model_path,
                    }
                )

            duration = (datetime.now() - start_time).total_seconds()

            # Log the outputs
            span.set_outputs(
                {
                    "status": "success",
                    "model_count": len(models),
                    "duration_seconds": duration,
                }
            )

            return {"models": models}

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Error retrieving models: {str(e)}"

            span.set_outputs(
                {
                    "status": "error",
                    "error_msg": error_msg,
                    "duration_seconds": duration,
                    "exception": str(e),
                }
            )

            raise HTTPException(status_code=500, detail=error_msg)


@app.get("/models/{model_id}/ifc")
async def get_ifc_file(model_id: int):
    """
    Download the IFC file for a specific model.

    Args:
        model_id: The ID of the model to download

    Returns:
        FileResponse: The IFC file as a download
    """
    start_time = datetime.now()

    with mlflow.start_span(name="API_get_ifc_file", span_type="API") as span:
        # Log the inputs
        span.set_inputs(
            {
                "model_id": model_id,
                "timestamp": start_time.isoformat(),
            }
        )

        try:
            # Get the IFC model information from the database (run in threadpool)
            ifc_model = await run_in_threadpool(partial(get_ifc_model, id=model_id))

            if not ifc_model:
                error_msg = f"BIM model with ID {model_id} not found"
                span.set_outputs(
                    {
                        "status": "error",
                        "error_msg": error_msg,
                        "duration_seconds": (
                            datetime.now() - start_time
                        ).total_seconds(),
                    }
                )
                raise HTTPException(status_code=404, detail=error_msg)

            if not ifc_model.model_path or not os.path.exists(ifc_model.model_path):
                error_msg = f"BIM model file not found at path: {ifc_model.model_path}"
                span.set_outputs(
                    {
                        "status": "error",
                        "error_msg": error_msg,
                        "duration_seconds": (
                            datetime.now() - start_time
                        ).total_seconds(),
                    }
                )
                raise HTTPException(status_code=404, detail=error_msg)

            # Log model information
            span.set_attributes(
                {
                    "model_path": ifc_model.model_path,
                    "project_name": ifc_model.project_name,
                    "model_name": ifc_model.model_name,
                }
            )

            duration = (datetime.now() - start_time).total_seconds()

            # Log the outputs
            span.set_outputs(
                {
                    "status": "success",
                    "model_path": ifc_model.model_path,
                    "duration_seconds": duration,
                }
            )

            # Generate a filename for the download
            filename = f"{ifc_model.project_name}_{ifc_model.model_name}_{model_id}.ifc"
            # Clean filename of any invalid characters
            filename = "".join(c for c in filename if c.isalnum() or c in "._-")

            return FileResponse(
                path=ifc_model.model_path,
                filename=filename,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Handle any other unexpected errors
            error_msg = f"An unexpected error occurred: {str(e)}"
            duration = (datetime.now() - start_time).total_seconds()

            span.set_outputs(
                {
                    "status": "error",
                    "error_msg": error_msg,
                    "duration_seconds": duration,
                    "exception": str(e),
                }
            )

            print(f"Error in get_ifc_file: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")

            raise HTTPException(status_code=500, detail=error_msg)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
