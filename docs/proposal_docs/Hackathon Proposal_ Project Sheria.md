Hackathon Proposal: Project Sheria

Document Title: Siloed Data, Static Rules: Bridging the Gap Between Citizen Services and Actionable Insights with a Rule-Driven AI Agent

Hackathon Track: Generative & Agentic AI – Localized and contextualized LLMs for education, healthcare, and governance.

1.0 The Problem: Data-Rich, Insight-Poor Governance

Government agencies in Kenya possess vast amounts of citizen data, spanning land title applications, health records, and service requests. However, this data is often locked away in heterogeneous formats like PDFs, raw databases, and scanned forms. Compounding this issue, the business logic that governs services—such as, "IF a land application is missing a signature, THEN it is put on hold"—exists only as static, manually-coded rules or, worse, as unwritten knowledge in the minds of seasoned staff.

This situation creates critical bottlenecks for all stakeholders:

\- For Government Officers: They lack dynamic decision support. Manually cross-referencing rules and data to predict service outcomes (e.g., "What is the expected approval time for this permit?") leads to significant delays and inconsistent service delivery.

\- For Citizens: Service processes are opaque "black boxes." A citizen cannot ask, "Why was my business license delayed?" and receive a clear, evidence-based explanation, leading to frustration and a lack of trust.

\- For Policymakers: Aggregating data to forecast trends (e.g., "Which clinic will have the highest patient load next month?") is a slow, separate analytical process, hindering proactive and data-driven resource allocation.

In essence, there is a missing conversational layer that can intelligently bridge raw data, domain-specific rules, and the people who need answers.

2.0 Our Proposed Solution: "Sheria"

We propose Sheria (the Swahili word for "Law" or "Rule"), a rule-driven, conversational AI agent designed to transform static data and rules into a dynamic, intelligent partner for public service.

Sheria is built on a localized Large Language Model (LLM) fine-tuned on Kenyan administrative text and Swahili, ensuring it deeply understands local context, jargon, and processes.

2.1 How Sheria Works

1\. Intelligent Ingestion & Parsing:  
   \- Sheria ingests raw data from various sources (PDFs, database records, scanned forms).  
   \- It uses OCR (Optical Character Recognition) and custom parsers to extract key entities such as Applicant Name, Date, and Document Type.

2\. Natural Language Rule Translation:  
   \- Domain experts can define business rules in a simple, declarative format (e.g., IF document\_type \= "Birth\_Certificate" AND applicant\_age \< 18 THEN require\_guardian\_signature).  
   \- Sheria's LLM translates these natural language rules into executable code for the system's rule engine.

3\. Agentic Reasoning & Orchestration:  
   \- When a user submits a query, Sheria's AI agent orchestrates a multi-step process:  
     \- Retrieval: Fetches all relevant citizen data and applicable business rules.  
     \- Reasoning: Evaluates the rules against the data and combines them with statistical models to generate predictions and insights.  
     \- Response Generation: Formulates a clear, natural language answer.

4\. Conversational User Interface:  
   \- A simple chat interface allows users to ask questions in English, Swahili, or Sheng.  
   \- Example Officer Query: "Show me all land applications in Kajiado that are at high risk of delay."  
   \- Example Citizen Query & Response:  
     \- Query: "Why is my water connection request pending?"  
     \- Sheria’s Reply: "Your request (Reference \#AB-123) is pending because the required site survey report is missing. The average resolution time for this issue is 5 days. Please contact the planning department for further assistance."

3.0 Key Features & Innovations

\- Contextualized LLM: Our model is specifically fine-tuned on Kenyan government documents, enabling superior understanding of local processes, terminology, and language.

\- Rule-Driven Transparency: Every decision and forecast is backed by citable domain rules, moving beyond a "black box" model to build trust, accountability, and clarity.

\- Agentic Workflow: The system autonomously performs complex, multi-step reasoning (Retrieve \-\> Evaluate \-\> Predict \-\> Explain), requiring minimal human intervention.

\- Multilingual Citizen Engagement: By breaking down language barriers, Sheria makes government services accessible and understandable to a much wider population.

4.0 Target Beneficiaries

\- Government Agencies: (e.g., Ministry of Lands, National Housing Corporation, County Health Services) will benefit from faster, more consistent, and fully auditable decision-making.

\- Citizens: Will receive immediate, transparent, and multilingual explanations for service statuses and outcomes, empowering them with information.

\- Policy Makers: Can query aggregated, rule-based forecasts to better understand trends and guide proactive public resource allocation.

5.0 Proposed Tech Stack

\- Data Ingestion & OCR: Tesseract OCR, Custom Parsers (for PDFs and forms)

\- Metadata & Rule Storage: PostgreSQL with JSONB for flexible data structuring

\- Rule Engine: Python-based Predicate Logic (translated from a simple Domain-Specific Language)

\- Localized LLM Core: LLaMA-2 or Falcon, fine-tuned on Kenyan administrative text

\- Agent Orchestration Framework: LangChain or LlamaIndex

\- User Interface: React-based web application with internationalization (i18n) for English and Swahili

6.0 Alignment with Hackathon Goals

This solution directly addresses the core objectives of the Generative & Agentic AI track:

\- Localized & Contextualized LLMs: The core of our solution is an LLM specifically tuned for the Kenyan public sector context.

\- Generative & Agentic AI: Sheria generates predictions, explanations, and insights, operating autonomously through a sophisticated multi-step agentic loop.

\- Impact on Governance: It directly enhances transparency, operational efficiency, and citizen engagement in critical government services.