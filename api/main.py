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
from src.agents.cobbie import cobbie
from src.config import MLFLOW_URI

# from src.db.query_db import get_ifc_models
from src.db.query import get_ifc_model, get_ifc_models
from src.tools.initial import query_ifcopenshell_docs, web_search
from src.util import get_created_tools

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


def load_tools():
    """Load both initial and created tools for COBBIE."""
    # Start with initial tools
    initial_tools = [query_ifcopenshell_docs, web_search]

    # Load dynamically created tools from src/tools/created/
    all_tools = get_created_tools(tools=initial_tools)

    return all_tools





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
    with mlflow.start_run(run_name=run_name):
        # Create a nested run for the engine execution (this is where traces will be stored)
        engine_run_name = f"Engine_{request.model_id}_{datetime.now().strftime('%H%M%S')}"
        with mlflow.start_run(run_name=engine_run_name, nested=True):
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

                    # Load tools for COBBIE
                    tools = load_tools()

                    # Use COBBIE to answer the question (run in threadpool)
                    final_answer, collector, execution_history = await run_in_threadpool(
                        partial(
                            cobbie,
                            user_input=request.question,
                            tools=tools,
                            max_iterations=15,
                            model_path=ifc_model.model_path,
                            llm_provider="zai",
                            llm_name="GLM-4.6",
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

                    # Determine status based on answer content
                    status = (
                        "success"
                        if "iteration limit" not in final_answer.answer.lower()
                        else "error"
                    )
                    error_msg = (
                        final_answer.answer
                        if status == "error"
                        else None
                    )

                    # Extract token usage from collector
                    input_tokens = 0
                    output_tokens = 0
                    if collector and hasattr(collector, "usage") and collector.usage:
                        usage = collector.usage
                        input_tokens = usage.input_tokens or 0
                        output_tokens = usage.output_tokens or 0

                    # Log the outputs
                    span.set_outputs(
                        {
                            "status": status,
                            "answer": final_answer.answer if status == "success" else None,
                            "error_msg": error_msg,
                            "duration_seconds": duration,
                            "model_info": model_info,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        }
                    )

                    return QuestionResponse(
                        status=status,
                        answer=final_answer.answer if status == "success" else None,
                        error_msg=error_msg,
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
