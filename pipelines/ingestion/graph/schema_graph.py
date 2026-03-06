# pipelines/ingestion/graph/schema_graph.py
from typing import Literal

# --- Node Labels ---
# Restricted to Kenya judicial domain entities only.
VALID_NODE_LABELS = Literal[
    "Case",           # Court case, e.g. "Muiruri v Republic [2021] KESC 12"
    "Judge",          # Presiding judge or magistrate
    "Court",          # Court of jurisdiction (Supreme Court, Court of Appeal, High Court)
    "Party",          # Litigant: Plaintiff, Defendant, Appellant, Respondent
    "Advocate",       # Legal counsel / representative
    "Statute",        # Act of Parliament, Regulation, or Subsidiary Legislation
    "LegalPrinciple", # Ratio decidendi, legal test, or legal doctrine
    "Judgment",       # Written decision or ruling document
    "CourtOrder",     # Specific orders or directions issued by a court
]

# --- Edge Types ---
# Restricted to Kenya judicial relationships only.
VALID_RELATION_TYPES = Literal[
    "CITES",          # Case cites another case as authority
    "OVERRULES",      # Case overrules a prior decision
    "DISTINGUISHES",  # Case distinguishes itself from a precedent
    "APPLIES",        # Case applies a statute or legal principle
    "INTERPRETS",     # Case interprets a statute's meaning
    "APPEALED_TO",    # Case was appealed to a higher court
    "PRESIDED_BY",    # Case was heard by a judge
    "FILED_IN",       # Case was filed in a court
    "REPRESENTS",     # Advocate represents a party in a case
    "BINDS",          # Higher court decision binds a lower court
]


class GraphSchema:
    """
    Central source of truth for the Kenya Judicial Knowledge Graph schema.
    Used by GraphExtractor to inject schema constraints into the LLM prompt.
    """

    @staticmethod
    def get_system_prompt() -> str:
        node_labels = list(VALID_NODE_LABELS.__args__)
        relation_types = list(VALID_RELATION_TYPES.__args__)

        return f"""You are a Kenya judicial knowledge graph extraction engine specializing in Kenya Law Reports (Supreme Court, Court of Appeal, High Court).

Your task is to extract named entities (nodes) and relationships (edges) from Kenyan legal text.

## Allowed Node Types
Only use these labels — do NOT invent new types:
{chr(10).join(f"  - {label}" for label in node_labels)}

Node ID rules:
- Case nodes: use Kenya citation format, e.g. "Muiruri v Republic [2021] KESC 12"
- Judge nodes: use full name, e.g. "Justice M.K. Ibrahim"
- Statute nodes: use full act name, e.g. "Land Registration Act No. 3 of 2012"
- All other nodes: use the canonical name as it appears in the text

## Allowed Relationship Types
Only use these — do NOT invent new types:
{chr(10).join(f"  - {rel}" for rel in relation_types)}

## Output Format
Return ONLY valid JSON. No explanation, no markdown, no extra text.

{{
  "nodes": [
    {{"id": "<canonical name>", "type": "<NodeLabel>"}}
  ],
  "edges": [
    {{"source": "<node id>", "target": "<node id>", "type": "<RELATION_TYPE>"}}
  ]
}}

## Example
Input: "In Muiruri v Republic [2021] KESC 12, Justice Ibrahim applied the adverse possession doctrine from the Land Registration Act, overruling the Court of Appeal's earlier decision in Kamau v Wanjiku [2015] KECA 44."

Output:
{{
  "nodes": [
    {{"id": "Muiruri v Republic [2021] KESC 12", "type": "Case"}},
    {{"id": "Justice Ibrahim", "type": "Judge"}},
    {{"id": "Adverse Possession", "type": "LegalPrinciple"}},
    {{"id": "Land Registration Act No. 3 of 2012", "type": "Statute"}},
    {{"id": "Kamau v Wanjiku [2015] KECA 44", "type": "Case"}},
    {{"id": "Supreme Court", "type": "Court"}}
  ],
  "edges": [
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Justice Ibrahim", "type": "PRESIDED_BY"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Adverse Possession", "type": "APPLIES"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Land Registration Act No. 3 of 2012", "type": "APPLIES"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Kamau v Wanjiku [2015] KECA 44", "type": "OVERRULES"}}
  ]
}}"""
