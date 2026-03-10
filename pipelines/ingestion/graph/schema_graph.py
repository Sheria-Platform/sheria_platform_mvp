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
    "Constitution",   # Kenya Constitution (supreme law, distinct from ordinary Statute)
    "LegalIssue",     # Specific legal question raised in a case
    "CourtRegistry",  # Physical registry/location, e.g. "High Court — Nairobi"
    "Offence",        # Criminal charge or offence, e.g. "Murder contrary to section 203 Penal Code"
    "Evidence",       # A piece of evidence tendered or relied upon in proceedings
    "Remedy",         # Relief sought or granted, e.g. "Injunction", "Certiorari", "Damages"
]

# --- Edge Types ---
# Restricted to Kenya judicial relationships only.
VALID_RELATION_TYPES = Literal[

    # ── Citation / Precedent ─────────────────────────────────────────────────
    "CITES",              # Case cites another case as authority
    "OVERRULES",          # Case overrules a prior decision (replaces law)
    "DISTINGUISHES",      # Case distinguishes itself from a precedent
    "FOLLOWS",            # Case explicitly follows another case's reasoning
    "AFFIRMED",           # Higher court affirmed lower court ruling
    "REVERSED",           # Higher court reversed lower court ruling
    "APPROVED",           # Court approved the reasoning in another case (weaker than AFFIRMED)
    "DOUBTED",            # Court expressed doubt about a case without overruling it
    "DEPARTED_FROM",      # Court departed from prior practice without formally overruling
    "ADOPTED",            # Court adopted a principle from another jurisdiction
    "CONSIDERED",         # Case was cited and considered but not directly followed

    # ── Procedural ───────────────────────────────────────────────────────────
    "APPEALED_TO",        # Case was appealed to a higher court
    "PRESIDED_BY",        # Case was heard/presided over by a judge
    "FILED_IN",           # Case was filed in a court registry
    "DECIDED_BY",         # Case was finally decided by a court
    "GRANTED",            # Court granted an application, order, or relief
    "DISMISSED",          # Court dismissed a case or application
    "STRUCK_OUT",         # Pleading or case struck out for procedural defect
    "STAYED",             # Proceedings or order stayed pending appeal or compliance
    "CONSOLIDATED_WITH",  # Two or more cases consolidated and heard together
    "REFERRED_TO",        # Matter referred to another court, tribunal, or body
    "REMITTED_TO",        # Matter remitted to a lower court for rehearing
    "WITHDRAWN_FROM",     # Party withdrew matter from proceedings
    "JOINED_AS",          # Party joined as interested party, amicus curiae, or co-respondent

    # ── Legal Authority ───────────────────────────────────────────────────────
    "APPLIES",            # Case applies a statute or legal principle
    "INTERPRETS",         # Case interprets a statute's meaning
    "BINDS",              # Higher court decision binds a lower court
    "GOVERNS",            # Constitution/Statute governs a legal principle or area
    "VIOLATED",           # Party or state violated a right, statute, or court order
    "NULLIFIED",          # Court nullified a law, act, or instrument
    "DECLARED",           # Court made a declaratory order (e.g. rights, status, constitutionality)
    "ENFORCES",           # Court or body enforces a statute or prior order

    # ── Criminal Law ─────────────────────────────────────────────────────────
    "CHARGED_WITH",       # Accused charged with a specific offence
    "PROSECUTED_BY",      # Party prosecuted by the state or DPP
    "CONVICTED",          # Court convicted the accused of an offence
    "ACQUITTED",          # Court acquitted the accused
    "SENTENCED",          # Court sentenced a convicted party
    "ARRESTED_BY",        # Person arrested by a law enforcement body
    "DETAINED_BY",        # Person detained by authority (remand, custody)
    "GRANTED_BAIL",       # Court granted bail to accused pending trial or appeal

    # ── Civil / Constitutional ────────────────────────────────────────────────
    "PETITIONED",         # Party filed a constitutional petition against another
    "CHALLENGED",         # Party challenged a law, decision, or act
    "CLAIMED_AGAINST",    # Party made a civil claim against another
    "AWARDED_TO",         # Damages, costs, or compensation awarded to a party
    "ENJOINED",           # Party restrained by injunction from doing an act

    # ── Land / Property ───────────────────────────────────────────────────────
    "OWNS",               # Party owns land or property
    "CLAIMS_TITLE_TO",    # Party claims ownership or title to land/property
    "REGISTERED_TO",      # Title/instrument registered in a party's name
    "TRANSFERRED_TO",     # Property or interest transferred to a party

    # ── Contract / Commercial ─────────────────────────────────────────────────
    "CONTRACTED_WITH",    # Parties in a contractual relationship
    "BREACHED",           # Party breached a contract, duty, or court order

    # ── Family Law ────────────────────────────────────────────────────────────
    "MARRIED_TO",         # Matrimonial relationship between parties
    "GUARDIAN_OF",        # Guardianship or custody relationship

    # ── Party / Representation ────────────────────────────────────────────────
    "REPRESENTS",         # Advocate represents a party in a case

    # ── Document ──────────────────────────────────────────────────────────────
    "ISSUED_BY",          # Judgment/CourtOrder was issued by a court

    # ── Issue ─────────────────────────────────────────────────────────────────
    "RAISES",             # Case raises a specific legal issue

    # ── Labor / Employment ────────────────────────────────────────────────────
    "EMPLOYS",            # Employer employs a party
    "LOCKS_OUT",          # Employer locks out workers (industrial dispute)
    "NEGOTIATES_WITH",    # Parties negotiate (collective bargaining)
    "DENIES",             # Court/party denies an application or appeal
    "OPPOSES",            # Party opposes a motion or application
    "ALLEGED",            # Party makes an allegation against another
    "DISREGARDED",        # Court/party disregarded a binding order or evidence
    "INVESTIGATED",       # Body investigated a party or incident
    "APPOINTED",          # Official appointed to a position (judge, registrar)
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

        return f"""You are a Kenya judicial knowledge graph extraction engine specializing in Kenya Law Reports (Supreme Court, Court of Appeal, High Court, Employment and Labour Relations Court, Environment and Land Court, Magistrates Courts).

Your task is to extract named entities (nodes) and relationships (edges) from Kenyan legal text.

## Allowed Node Types
Only use these labels — do NOT invent new types:
{chr(10).join(f"  - {label}" for label in node_labels)}

Node ID rules:
- Case nodes: use Kenya citation format, e.g. "Muiruri v Republic [2021] KESC 12"
- Judge nodes: use full name, e.g. "Justice M.K. Ibrahim"
- Statute nodes: use full act name, e.g. "Land Registration Act No. 3 of 2012"
- Offence nodes: use the charge as stated, e.g. "Murder contrary to section 203 of the Penal Code"
- Remedy nodes: use the relief type, e.g. "Certiorari", "Injunction", "General Damages"
- Constitution nodes: use "Constitution of Kenya 2010" or "Constitution of Kenya (Repealed)"
- LegalIssue nodes: use the precise question as stated, e.g. "Whether adverse possession applies to registered land"
- CourtRegistry nodes: use court + city, e.g. "High Court — Nairobi", "Magistrate Court — Kisumu"
- All other nodes: use the canonical name as it appears in the text

## Allowed Relationship Types
Only use these — do NOT invent new types:
{chr(10).join(f"  - {rel}" for rel in relation_types)}

## Choosing the right relationship — guidance by domain

**Citation hierarchy (use the most precise):**
- OVERRULES > REVERSED > AFFIRMED > APPROVED > FOLLOWS > DISTINGUISHED > DOUBTED > CONSIDERED > CITES
- Use ADOPTED when importing a principle from a foreign or persuasive jurisdiction
- Use DEPARTED_FROM when a court changes practice without formally overruling

**Procedural outcomes (mutually exclusive per application):**
- GRANTED / DISMISSED — final outcome of an application or case
- STRUCK_OUT — procedural dismissal (no cause of action, abuse of process)
- STAYED — proceedings suspended, not ended
- WITHDRAWN_FROM — party voluntarily discontinues

**Criminal law chain:**
- CHARGED_WITH → PROSECUTED_BY → CONVICTED/ACQUITTED → SENTENCED
- Use ARRESTED_BY / DETAINED_BY for pre-trial deprivation of liberty
- Use GRANTED_BAIL for bail orders

**Constitutional / civil:**
- PETITIONED — for constitutional petitions under Article 22/258
- CHALLENGED — judicial review or statutory challenge
- VIOLATED — breach of a constitutional right or statute
- DECLARED — declaratory relief (e.g. "null and void", "unconstitutional")
- NULLIFIED — instrument/law set aside entirely
- AWARDED_TO — monetary or specific relief given to a party
- ENJOINED — injunctive relief restraining a party

## Do NOT use these (common mistakes):
- RELATED_TO, REFERS_TO, RELATES_TO, APPLIES_TO — too vague; use CITES or APPLIES instead
- INVOLVES, CAUSES, AFFECTS, COMMUNICATES_WITH — too vague; pick the most specific type
- AFFIRMS — use AFFIRMED (canonical past-tense form)
- OPPOSED — use OPPOSES instead
- REPORTS_TO, WORKS_AT — use EMPLOYS or APPOINTED instead
- COMPETITOR, OPPONENT — not legal relationships; use Party node type
- RECEIVES — use AWARDED_TO or GRANTED instead
- NONE, N/A, DATE, TIMESTAMP, SECTION, ARTICLE — not relationships
- JUDGMENT, CASE, JUDGE, PARTY — these are node types, not relationship types

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
Input: "In Muiruri v Republic [2021] KESC 12, Justice Ibrahim applied the adverse possession doctrine from the Land Registration Act, overruling the Court of Appeal's earlier decision in Kamau v Wanjiku [2015] KECA 44. The court also considered whether the right to property under Article 40 of the Constitution of Kenya 2010 governs the adverse possession principle."

Output:
{{
  "nodes": [
    {{"id": "Muiruri v Republic [2021] KESC 12", "type": "Case"}},
    {{"id": "Justice Ibrahim", "type": "Judge"}},
    {{"id": "Adverse Possession", "type": "LegalPrinciple"}},
    {{"id": "Land Registration Act No. 3 of 2012", "type": "Statute"}},
    {{"id": "Kamau v Wanjiku [2015] KECA 44", "type": "Case"}},
    {{"id": "Supreme Court", "type": "Court"}},
    {{"id": "Constitution of Kenya 2010", "type": "Constitution"}},
    {{"id": "Whether adverse possession applies to registered land", "type": "LegalIssue"}}
  ],
  "edges": [
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Justice Ibrahim", "type": "PRESIDED_BY"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Adverse Possession", "type": "APPLIES"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Land Registration Act No. 3 of 2012", "type": "APPLIES"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Kamau v Wanjiku [2015] KECA 44", "type": "OVERRULES"}},
    {{"source": "Muiruri v Republic [2021] KESC 12", "target": "Whether adverse possession applies to registered land", "type": "RAISES"}},
    {{"source": "Constitution of Kenya 2010", "target": "Adverse Possession", "type": "GOVERNS"}}
  ]
}}"""
