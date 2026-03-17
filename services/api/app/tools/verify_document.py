# services/api/app/tools/verify_document.py
"""Sheria Verify — court document authentication tool.

Performs a three-step verification pipeline:
    1. LLM metadata extraction  (court, judge, date, parties, case_number)
    2. Qdrant cross-reference    (does this case exist in Kenya Law Reports?)
    3. LLM fraud analysis        (known forgery patterns check)

Produces a weighted confidence score and a ``VerificationReport`` JSON string
that is returned to both the HTTP route and the agent tool_node registry.

Confidence weights:
    - Metadata extraction success: 20%
    - Qdrant case law match found: 40%
    - LLM fraud analysis clean:   40%
"""

import json
import logging

from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.ollama_embeddings import embeddings_client
from services.api.app.clients.qdrant import qdrant_client

logger = logging.getLogger(__name__)

# ── Prompts ──────────────────────────────────────────────────────────────────

_METADATA_PROMPT = """\
You are a court document metadata extractor for the Kenyan judiciary.
Extract structured metadata from the following court document text.

Document type: {document_type}

Document text (first 3000 characters):
{document_text}

Output JSON only — no prose, no markdown fences:
{{
  "court": "<court name or empty string>",
  "judge": "<presiding judge(s) or empty string>",
  "date": "<document date ISO format or empty string>",
  "parties": "<parties involved or empty string>",
  "case_number": "<case number or empty string>",
  "document_summary": "<one-sentence summary>"
}}"""

_FRAUD_PROMPT = """\
You are a Kenyan court document fraud detector.
Check the document snippet below for forgery signs.

Type: {document_type} | User case#: {case_number}
Metadata: {extracted_metadata}

Snippet: {document_text}

Forgery signs to check: wrong case# prefix for court type, impossible dates, \
fabricated judge names, non-standard citations, missing mandatory sections, \
internal case# contradictions.

Respond with JSON only:
{{"fraud_indicators_found": false, "risk_level": "low", "flags": [], "analysis": "brief reason"}}

risk_level: low | medium | high"""

# ── Confidence weights ────────────────────────────────────────────────────────

_W_METADATA = 0.20
_W_QDRANT = 0.40
_W_FRAUD = 0.40

# Qdrant similarity threshold for a "match"
_MATCH_THRESHOLD = 0.70


# ── Main entry-point ─────────────────────────────────────────────────────────


async def verify_document(tool_input: str) -> str:
    """Verify a court document and return a ``VerificationReport`` JSON string.

    Accepts a JSON string so it can be called identically from:
    - The HTTP route (``routes/verify.py``)
    - The agent tool_node registry (``agents/nodes/tool.py``)

    Args:
        tool_input: JSON string with keys:
            ``document_text``  — raw extracted text from the PDF
            ``document_type``  — e.g. ``"court_order"``, ``"judgment"``
            ``case_number``    — case reference supplied by the user (may be empty)

    Returns:
        JSON string conforming to the VerificationReport schema.
    """
    try:
        params = json.loads(tool_input)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid tool_input JSON: {exc}"})

    document_text: str = params.get("document_text", "")
    document_type: str = params.get("document_type", "court_order")
    case_number: str = params.get("case_number", "")

    checks: list[dict] = []
    risk_flags: list[str] = []
    score: float = 0.0

    # ── Step 1: Metadata extraction ───────────────────────────────────────
    extracted_metadata: dict = {}
    metadata_passed = False
    try:
        raw = await ollama_client.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": _METADATA_PROMPT.format(
                        document_type=document_type,
                        document_text=document_text[:3000],
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=512,
            json_mode=True,
        )
        extracted_metadata = json.loads(raw)
        metadata_passed = bool(
            extracted_metadata.get("court")
            or extracted_metadata.get("case_number")
            or extracted_metadata.get("date")
        )
        detail = (
            f"Extracted: court={extracted_metadata.get('court')!r}, "
            f"judge={extracted_metadata.get('judge')!r}, "
            f"date={extracted_metadata.get('date')!r}"
        )
    except Exception as exc:
        logger.warning("Metadata extraction failed: %s", exc)
        detail = f"Extraction failed: {exc}"

    checks.append(
        {
            "check": "metadata_extraction",
            "passed": metadata_passed,
            "detail": detail,
        }
    )
    if metadata_passed:
        score += _W_METADATA

    # ── Step 2: Qdrant case-law cross-reference ───────────────────────────
    qdrant_passed = False
    qdrant_detail = "No case law match found in Kenya Law Reports."
    try:
        # Use the case number if available, otherwise the first 500 chars of text
        query_text = case_number or document_text[:500]
        vector = await embeddings_client.embed_query(query_text)
        hits = await qdrant_client.search(vector=vector, limit=3)

        if hits and hits[0].score >= _MATCH_THRESHOLD:
            qdrant_passed = True
            top = hits[0]
            payload = top.payload or {}
            qdrant_detail = (
                f"Case found in Kenya Law Reports. "
                f"Top match score={top.score:.3f}, "
                f"source={payload.get('source', 'unknown')!r}"
            )
        elif hits:
            qdrant_detail = (
                f"Closest match score={hits[0].score:.3f} is below "
                f"threshold {_MATCH_THRESHOLD} — case not confirmed."
            )
    except Exception as exc:
        logger.warning("Qdrant cross-reference failed: %s", exc)
        qdrant_detail = f"Vector search error: {exc}"

    checks.append(
        {
            "check": "case_law_match",
            "passed": qdrant_passed,
            "detail": qdrant_detail,
        }
    )
    if qdrant_passed:
        score += _W_QDRANT

    # ── Step 3: LLM fraud analysis ────────────────────────────────────────
    fraud_passed = False
    fraud_detail = "Fraud analysis inconclusive."
    try:
        raw = await ollama_client.chat_completion(
            messages=[
                {
                    "role": "user",
                    "content": _FRAUD_PROMPT.format(
                        document_type=document_type,
                        case_number=case_number,
                        extracted_metadata=json.dumps(extracted_metadata),
                        document_text=document_text[:800],
                    ),
                }
            ],
            temperature=0.0,
            max_tokens=1024,
            json_mode=True,
        )
        fraud_data = json.loads(raw)
        fraud_indicators = fraud_data.get("fraud_indicators_found", True)
        risk_level = fraud_data.get("risk_level", "medium")
        flags = fraud_data.get("flags", [])
        analysis = fraud_data.get("analysis", "")

        fraud_passed = not fraud_indicators and risk_level == "low"
        fraud_detail = f"Risk: {risk_level}. {analysis}"
        risk_flags.extend(flags)
    except Exception as exc:
        logger.warning("Fraud analysis failed: %s", exc)
        fraud_detail = f"Fraud analysis error: {exc}"

    checks.append(
        {
            "check": "fraud_analysis",
            "passed": fraud_passed,
            "detail": fraud_detail,
        }
    )
    if fraud_passed:
        score += _W_FRAUD

    # ── Compose report ────────────────────────────────────────────────────
    authentic = score >= 0.60  # at least 2 of 3 checks passed

    if authentic and not risk_flags:
        summary = f"Document appears authentic (confidence {score:.0%}). Case confirmed in Kenya Law Reports."
    elif authentic:
        summary = f"Document likely authentic (confidence {score:.0%}) but has minor risk flags: {'; '.join(risk_flags)}."
    else:
        summary = f"Document authenticity uncertain (confidence {score:.0%}). Further manual verification recommended."

    report = {
        "authentic": authentic,
        "confidence": round(score, 2),
        "document_type": document_type,
        "extracted_metadata": extracted_metadata,
        "verification_checks": checks,
        "risk_flags": risk_flags,
        "summary": summary,
    }

    logger.info(
        "Verification complete",
        extra={
            "authentic": authentic,
            "confidence": score,
            "document_type": document_type,
            "case_number": case_number,
        },
    )
    return json.dumps(report)
