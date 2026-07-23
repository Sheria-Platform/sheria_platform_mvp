# services/api/app/tools/predict_case_duration.py
"""Sheria Predict — case duration forecasting tool.

Performs a two-step prediction pipeline:
    1. Qdrant historical analogy retrieval  (similar cases by embedding)
    2. LLM duration synthesis               (estimate + confidence + risk factors)

Confidence weights are implicit in the LLM synthesis — more analogies retrieved
from Kenya Law Reports → higher confidence output.

Returns a ``PredictionReport`` JSON string callable identically from:
- The HTTP route (``routes/predict.py``)
- The agent tool_node registry (``agents/nodes/tool.py``)
"""

import json
import logging
import re

from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.ollama_embeddings import embeddings_client
from services.api.app.clients.qdrant import qdrant_client

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Strip optional markdown fences and return the inner JSON string.

    Raises:
        ValueError: If the response is empty after stripping.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("LLM returned an empty response")
    m = _JSON_FENCE_RE.search(raw)
    return m.group(1) if m else raw


# ── Prompt ────────────────────────────────────────────────────────────────────

_PREDICTION_PROMPT = """\
You are a Kenyan judicial analytics expert specialising in case duration forecasting.

A court staff member has submitted the following case attributes for duration estimation:

Case type:       {case_type}
Court:           {court}
Parties count:   {parties_count}
Complexity:      {complexity}
Description:     {description}

Historical analogies retrieved from Kenya Law Reports (up to 5 similar cases):
{analogies}

Based on the case attributes and historical analogies, produce a realistic duration forecast.

Consider these factors:
- Case type complexity (land disputes and commercial cases are typically longer)
- Court tier and location (Nairobi High Court has higher backlog)
- Number of parties (more parties = more procedural steps)
- Kenya judicial system norms (average High Court case: 12–36 months)

Output JSON only — no prose, no markdown fences:
{{
  "estimated_months_min": <integer — optimistic estimate>,
  "estimated_months_max": <integer — conservative estimate>,
  "confidence": <float 0.0–1.0>,
  "similar_cases_found": <integer — number of analogies used>,
  "key_factors": [<list of 2–4 strings — factors most influencing this estimate>],
  "risk_level": "low" | "medium" | "high" | "critical",
  "summary": "<one sentence human-readable forecast>"
}}

risk_level guide:
  low      — straightforward legal issue, few parties, common case type
  medium   — moderate complexity or parties, some procedural risk
  high     — multi-party, constitutional issues, expert witnesses, or high-backlog court
  critical — very_high complexity, 5+ parties, constitutional or precedent-setting matter"""


# ── Main entry-point ──────────────────────────────────────────────────────────


async def predict_case_duration(tool_input: str) -> str:
    """Forecast the duration of a court case and return a ``PredictionReport`` JSON string.

    Accepts a JSON string so it can be called identically from:
    - The HTTP route (``routes/predict.py``)
    - The agent tool_node registry (``agents/nodes/tool.py``)

    Args:
        tool_input: JSON string with keys:
            ``case_type``      — e.g. ``"land_dispute"``, ``"criminal"``, ``"family"``
            ``court``          — e.g. ``"High Court Nairobi"``
            ``parties_count``  — integer number of parties (default 2)
            ``complexity``     — ``"low"`` | ``"medium"`` | ``"high"`` (default ``"medium"``)
            ``description``    — optional free-text case summary (may be empty)

    Returns:
        JSON string conforming to the PredictionReport schema, or
        ``{"error": "..."}`` if input is malformed or synthesis fails.
    """
    try:
        params = json.loads(tool_input)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid tool_input JSON: {exc}"})

    case_type: str = params.get("case_type", "general")
    court: str = params.get("court", "")
    parties_count: int = int(params.get("parties_count", 2))
    complexity: str = params.get("complexity", "medium")
    description: str = params.get("description", "")

    # ── Step 1: Retrieve historical analogies from Qdrant ─────────────────
    analogies_text = "No historical analogies available."
    similar_cases_found = 0
    try:
        # Embed a rich query combining all case attributes
        query_text = (
            f"{case_type} {complexity} complexity {court} "
            f"{parties_count} parties {description}"
        ).strip()
        vector = await embeddings_client.embed_query(query_text)
        hits = await qdrant_client.search(vector=vector, limit=5)

        if hits:
            similar_cases_found = len(hits)
            snippets: list[str] = []
            for i, hit in enumerate(hits, 1):
                payload = hit.payload or {}
                source = payload.get("source", "unknown")
                text_snippet = (payload.get("text", "") or "")[:300]
                snippets.append(
                    f"Analogy {i} (relevance={hit.score:.3f}, source={source!r}):\n{text_snippet}"
                )
            analogies_text = "\n\n".join(snippets)
    except Exception as exc:
        logger.warning("Qdrant analogy retrieval failed: %s", exc)
        analogies_text = f"Analogy retrieval unavailable: {exc}"

    # ── Step 2: LLM duration synthesis ───────────────────────────────────
    try:
        raw = await ollama_client.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": _PREDICTION_PROMPT.format(
                        case_type=case_type,
                        court=court or "Not specified",
                        parties_count=parties_count,
                        complexity=complexity,
                        description=description[:1000] if description else "Not provided",
                        analogies=analogies_text,
                    ),
                }
            ],
            temperature=0.1,
            max_tokens=768,
        )
        report = json.loads(_extract_json(raw))

        # Compute confidence deterministically so it actually varies with inputs.
        # Base: how many historical analogies did Qdrant find?
        _base_by_hits = {0: 0.25, 1: 0.45, 2: 0.60, 3: 0.72, 4: 0.82}
        base = _base_by_hits.get(similar_cases_found, 0.88 if similar_cases_found >= 5 else 0.25)

        # Adjust for complexity — more complex cases are harder to forecast accurately
        _complexity_delta = {"low": +0.07, "medium": 0.0, "high": -0.07, "very_high": -0.13}
        delta = _complexity_delta.get(complexity, 0.0)

        # Boost slightly if the user provided a description (more context = better prediction)
        description_boost = 0.03 if description else 0.0

        confidence = round(max(0.10, min(0.95, base + delta + description_boost)), 2)
        report["confidence"] = confidence
    except Exception as exc:
        logger.error("LLM prediction synthesis failed: %s", exc)
        return json.dumps({"error": f"Prediction synthesis failed: {exc}"})

    logger.info(
        "Case duration prediction complete",
        extra={
            "case_type": case_type,
            "court": court,
            "complexity": complexity,
            "estimated_months_min": report.get("estimated_months_min"),
            "estimated_months_max": report.get("estimated_months_max"),
            "confidence": report.get("confidence"),
            "risk_level": report.get("risk_level"),
        },
    )
    return json.dumps(report)
