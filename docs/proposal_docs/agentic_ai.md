
### **Problem Statement: Siloed Data, Static Rules: Bridging the Gap Between Citizen Services and Actionable Insights with a Rule-Driven AI Agent**

**Hackathon Track:** Generative & Agentic AI – Localized and contextualized LLMs for education, healthcare, and governance.

**The Problem:**
Government agencies in Kenya are data-rich but insight-poor. They manage vast repositories of citizen data—from land title applications and health records to service requests—locked in heterogeneous formats (PDFs, raw databases, scanned forms). The logic governing these services, such as "IF a land application is missing a signature, THEN it is put on hold," exists as static, manually-coded rules or, worse, only in the minds of seasoned staff.

This creates a critical bottleneck:
*   **For Officers:** They lack dynamic decision support. Predicting service outcomes (e.g., "What is the expected approval time for this permit?") requires manual cross-referencing of rules and data, leading to delays and inconsistencies.
*   **For Citizens:** Service processes are opaque "black boxes." A citizen cannot ask, "Why was my business license delayed?" and get a clear, evidence-based explanation.
*   **For Policymakers:** Aggregating data to forecast trends (e.g., "Which clinic will have the highest patient load next month?") is a slow, separate analytical process, hindering proactive resource allocation.

In essence, there is a missing "conversational layer" that can intelligently bridge raw data, domain-specific rules, and the people who need answers.

**Our Proposed Solution: "Sheria" - A Rule-Driven, Conversational AI Agent for Public Service**

We propose **Sheria** (the Swahili word for "Law" or "Rule"), an agentic AI platform that transforms static data and rules into a dynamic, conversational partner. Sheria is built on a localized LLM fine-tuned on Kenyan administrative text and Swahili, ensuring it understands local context and jargon.

**How It Works:**

1.  **Intelligent Ingestion:** Sheria ingests raw data (PDFs, DB records) and its metadata, using OCR and parsing to extract key entities (e.g., Applicant Name, Date, Document Type).
2.  **Rule Translation:** Domain experts can define business rules in a simple, declarative format (e.g., `IF document_type = "Birth_Certificate" AND applicant_age < 18 THEN require_guardian_signature`). Sheria's LLM translates these natural rules into executable code.
3.  **Agentic Reasoning:** When a query is received, Sheria's agent orchestrates a process of:
    *   **Retrieval:** Fetching relevant data and rules.
    *   **Reasoning:** Evaluating rules against the data and combining them with statistical models to generate predictions.
    *   **Response:** Formulating a natural language, multilingual answer.
4.  **Conversational Interface:** A simple chat UI allows users to ask questions in English, Swahili, or Sheng.
    *   **Officer Query:** "Show me all land applications in Kajiado that are at high risk of delay."
    *   **Citizen Query:** "Why is my water connection request pending?" → Sheria replies: "**Your request is pending because the required site survey report is missing. The average resolution time for this issue is 5 days. Please contact the planning department with your reference number AB-123.**"

**Key Features & Innovation:**

*   **Contextualized LLM:** Fine-tuned on Kenyan government documents for superior understanding of local processes and language.
*   **Rule-Driven Transparency:** Decisions and forecasts are not just predictions; they are backed by citable domain rules, building trust and accountability.
*   **Agentic Workflow:** The system autonomously performs multi-step reasoning (retrieve -> evaluate -> predict -> explain).
*   **Multilingual Citizen Engagement:** Breaks down language barriers, making services accessible to a wider population.

**Target Beneficiaries:**

*   **Government Agencies:** (e.g., Ministry of Lands, NHC, County Health Services) for faster, consistent, and auditable decision-making.
*   **Citizens:** Who receive immediate, transparent, and multilingual explanations for service statuses and outcomes.
*   **Policy Makers:** Who can query aggregated, rule-based forecasts to better guide public resource allocation.

**Tech Stack Implementation:**

*   **Data & OCR:** Tesseract, Custom Parsers (for PDFs, forms)
*   **Metadata Store:** PostgreSQL with JSONB
*   **Rule Engine:** Python-based Predicate Logic (translated from a simple DSL)
*   **Localized LLM:** LLaMA-2/Falcon fine-tuned on Kenyan administrative text
*   **Agent Orchestration:** LangChain/LlamaIndex
*   **Chat UI:** React with i18n (English, Swahili)

**Alignment with Hackathon Goals:**
This solution directly fulfills the core objectives:
*   **Localized & Contextualized LLMs:** Our model is specifically tuned for the Kenyan public sector context.
*   **Generative & Agentic AI:** Sheria generates predictions and explanations and operates autonomously through a multi-step agentic loop.
*   **Impact on Governance:** It enhances transparency, efficiency, and citizen engagement in government services.
