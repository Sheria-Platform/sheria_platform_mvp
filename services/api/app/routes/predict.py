# services/api/app/routes/predict.py
"""Sheria Predict -- case duration forecasting endpoint.

POST /api/v1/predict
    Accepts a JSON body with case attributes, runs the ``predict_case_duration``
    tool (Qdrant historical analogy retrieval + LLM synthesis), and returns
    a ``PredictionReport``.

GET /api/v1/predict/history
    Returns the authenticated user's prediction history, newest first.

No streaming -- prediction is a synchronous request/response.
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from services.api.app.auth.jwt import get_current_user
from services.api.app.auth.permissions import require_role
from services.api.app.dependencies import get_prediction_repo
from services.api.app.memory.prediction_repository import PredictionRepository
from services.api.app.tools.predict_case_duration import predict_case_duration

logger = logging.getLogger(__name__)

router = APIRouter()


# -- Request / Response models -------------------------------------------------


class PredictionRequest(BaseModel):
    case_type: str = Field(
        default="general",
        description=(
            "Type of case: land_dispute | criminal | family | "
            "commercial | constitutional | other"
        ),
        examples=["land_dispute"],
    )
    court: str = Field(
        default="",
        description="Court name and station, e.g. 'High Court Nairobi'",
        examples=["High Court Nairobi"],
    )
    parties_count: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Total number of parties (claimants + respondents)",
    )
    complexity: str = Field(
        default="medium",
        description="Estimated case complexity: low | medium | high",
        examples=["high"],
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Optional free-text summary of the legal issues in dispute",
    )


class PredictionReport(BaseModel):
    estimated_months_min: int
    estimated_months_max: int
    confidence: float
    similar_cases_found: int
    key_factors: list[str]
    risk_level: str
    summary: str


class PredictionActivity(BaseModel):
    id: int
    case_type: str
    court: str
    complexity: str
    parties_count: int
    estimated_months_min: int | None
    estimated_months_max: int | None
    confidence: float | None
    risk_level: str | None
    report: PredictionReport
    created_at: str


# -- Endpoints -----------------------------------------------------------------


@router.post(
    "",
    response_model=PredictionReport,
    summary="Predict case duration",
    description=(
        "Submit case attributes and receive a duration forecast. "
        "The pipeline retrieves similar historical cases from Kenya Law Reports (Qdrant) "
        "and synthesises an estimate via LLM with key risk factors."
    ),
)
async def predict_duration(
    request: PredictionRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_role("judge", "magistrate")),
    memory: PredictionRepository = Depends(get_prediction_repo),
) -> PredictionReport:
    """Forecast how long a court case is likely to take.

    Args:
        request:          Case attributes from the request body.
        background_tasks: FastAPI background task queue.
        user:             Authenticated user from JWT.
        memory:           Prediction repository dependency.

    Returns:
        ``PredictionReport`` with duration range, confidence, risk level,
        contributing factors, and a human-readable summary.

    Raises:
        HTTPException(422): If the prediction pipeline raises an
            unrecoverable error.
    """
    logger.info(
        "Case duration prediction requested",
        extra={
            "user_id": user.get("id"),
            "case_type": request.case_type,
            "court": request.court,
            "complexity": request.complexity,
            "parties_count": request.parties_count,
        },
    )

    tool_input = json.dumps(
        {
            "case_type": request.case_type,
            "court": request.court,
            "parties_count": request.parties_count,
            "complexity": request.complexity,
            "description": request.description,
        }
    )

    try:
        result_json = await predict_case_duration(tool_input)
        report_data = json.loads(result_json)
    except Exception as exc:
        logger.error("Prediction pipeline error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Prediction failed: {exc}",
        ) from exc

    if "error" in report_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=report_data["error"],
        )

    report = PredictionReport(**report_data)

    background_tasks.add_task(
        memory.save_prediction,
        user.get("id", ""),
        request.case_type,
        request.court,
        request.complexity,
        request.parties_count,
        report_data,
    )

    return report


@router.get(
    "/history",
    response_model=list[PredictionActivity],
    summary="List past case duration predictions",
    description="Return the authenticated user's prediction history, newest first.",
)
async def get_prediction_history(
    user: dict = Depends(get_current_user),
    memory: PredictionRepository = Depends(get_prediction_repo),
) -> list[PredictionActivity]:
    """Return prediction records for the current user.

    Args:
        user:   Authenticated user from JWT.
        memory: Prediction repository dependency.

    Returns:
        List of prediction dicts, newest first (up to 50).
    """
    return await memory.get_user_predictions(user.get("id", ""))
