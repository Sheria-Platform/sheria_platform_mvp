# services/api/app/tools/workload_management.py
"""Sheria Predict — workload management tool.

Queries the ``prediction_history`` table for a given court and time window,
aggregates statistics in Python, then uses the LLM to produce a one-sentence
narrative summary.

Returns a JSON string callable identically from:
- The agent tool_node registry (``agents/nodes/tool.py``)
- Future HTTP analytics routes
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from services.api.app.clients.ollama_client import ollama_client
from services.api.app.memory.prediction_repository import prediction_repository

logger = logging.getLogger(__name__)


async def workload_management(tool_input: str) -> str:
    """Return aggregate workload statistics for a court over a rolling time window.

    Args:
        tool_input: JSON string with keys:
            ``court`` — court name to analyse (e.g. ``"High Court — Nairobi"``).
            ``days``  — rolling window in days (default ``30``).

    Returns:
        JSON string with keys:
            court, period_days, total_cases_analysed, avg_predicted_months,
            high_risk_count, critical_risk_count, case_type_breakdown, summary.
        Returns ``{"error": "..."}`` on failure.
    """
    try:
        params = json.loads(tool_input)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid tool_input JSON: {exc}"})

    court: str = params.get("court", "")
    days: int = int(params.get("days", 30))

    if not court:
        return json.dumps({"error": "court is required"})

    since = datetime.now(tz=timezone.utc) - timedelta(days=days)

    try:
        records = await prediction_repository.get_court_predictions(court=court, since=since)
    except Exception as exc:
        logger.error("Failed to query prediction_history for court %r: %s", court, exc)
        return json.dumps({"error": f"Database query failed: {exc}"})

    total = len(records)

    if total == 0:
        summary = f"No prediction records found for {court!r} in the last {days} days."
        return json.dumps(
            {
                "court": court,
                "period_days": days,
                "total_cases_analysed": 0,
                "avg_predicted_months": None,
                "high_risk_count": 0,
                "critical_risk_count": 0,
                "case_type_breakdown": {},
                "summary": summary,
            }
        )

    # Aggregate in Python — no raw SQL
    month_midpoints: list[float] = []
    for r in records:
        lo = r.get("estimated_months_min")
        hi = r.get("estimated_months_max")
        if lo is not None and hi is not None:
            month_midpoints.append((lo + hi) / 2)

    avg_months = round(sum(month_midpoints) / len(month_midpoints), 1) if month_midpoints else None

    risk_counts = Counter(r.get("risk_level", "unknown") for r in records)
    high_risk_count = risk_counts.get("high", 0)
    critical_risk_count = risk_counts.get("critical", 0)

    case_type_breakdown = dict(Counter(r.get("case_type", "unknown") for r in records))

    # One-sentence LLM summary
    summary = ""
    try:
        prompt = (
            f"Summarise in one sentence the judicial workload for {court!r} "
            f"based on {total} cases analysed over the last {days} days. "
            f"Average predicted duration: {avg_months} months. "
            f"High-risk cases: {high_risk_count}. Critical-risk cases: {critical_risk_count}. "
            f"Case type breakdown: {case_type_breakdown}."
        )
        summary = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=128,
        )
        summary = summary.strip()
    except Exception as exc:
        logger.warning("LLM summary generation failed: %s", exc)
        summary = (
            f"{court} processed {total} cases in the last {days} days "
            f"with an average predicted duration of {avg_months} months."
        )

    result = {
        "court": court,
        "period_days": days,
        "total_cases_analysed": total,
        "avg_predicted_months": avg_months,
        "high_risk_count": high_risk_count,
        "critical_risk_count": critical_risk_count,
        "case_type_breakdown": case_type_breakdown,
        "summary": summary,
    }

    logger.info(
        "Workload management tool complete",
        extra={
            "court": court,
            "period_days": days,
            "total_cases_analysed": total,
            "high_risk_count": high_risk_count,
            "critical_risk_count": critical_risk_count,
        },
    )

    return json.dumps(result)
