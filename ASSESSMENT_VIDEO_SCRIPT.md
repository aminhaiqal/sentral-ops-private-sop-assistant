# 20-Minute Assessment Video Script

Use this script for a 15 to 20 minute recording. It is written for **Assessment Question 1:
Agentic RAG** and includes the phrases the evaluator is likely listening for: working
prototype, agentic retrieval, correct chunk retrieval, implementation flow, traditional RAG
versus agentic RAG, citations, retrieval optimization, Docker deployment, and testing
methodology.

## 0:00 - 0:45 Opening

Hello, my name is **[your name]**, and in this video I will present my solution for
**Question 1: Agentic RAG**.

For my prototype, I built a private knowledge assistant for a fictional operations company 
called Sentral Ops Supply Sdn. Bhd. The use case is simple and practical: staff can ask 
questions about internal SOPs, and the assistant answers only from approved company documents. 
It also shows citations, source snippets, guardrail warnings, and an Agent Trace so users can 
inspect how the answer was produced.

## 0:45 - 1:45 Problem And Goal

The business problem I am solving is that company SOP documents are often scattered across
files, onboarding guides, refund policies, finance processes, delivery escalation rules,
and data handling policies. Staff need quick answers, but the answer must be grounded in
approved documents.

A normal chatbot can sound confident even when it is wrong. That is risky for internal
operations. For example, a staff member might ask whether a payment is confirmed, whether
stock is available, or whether they can approve a refund. The assistant should not invent
live operational facts or make final approval decisions.

So the goal of this system is not just to answer questions. The goal is to answer from
approved SOP chunks, retrieve the correct supporting evidence, show citations, and refuse
or warn when the question requires live system checks, manager approval, confidential data
handling, or final decision authority.

## 1:45 - 3:00 High-Level Architecture

At a high level, the application has four main parts.

First, the frontend is built with **React and TypeScript**. It gives the user a simple chat
interface, demo questions, source cards, warning messages, and the Agent Trace.

Second, the backend is built with **FastAPI**. It exposes endpoints for health checks,
document ingestion, demo questions, and the main ask endpoint.

Third, the vector database is **Qdrant**. Qdrant stores the embedded SOP chunks and performs
similarity search when the user asks a question.

Fourth, the LLM layer uses **OpenAI**. The system uses an embedding model to embed both
documents and retrieval queries, and a chat model to synthesize the final answer from the
retrieved evidence.

The whole system can run with Docker Compose, which starts the backend, frontend, and
Qdrant together.

## 3:00 - 4:15 Why This Is Agentic RAG

Traditional RAG usually follows one fixed path. The user question is embedded, the top-k
chunks are retrieved, those chunks are placed into the prompt, and the LLM generates an
answer.

That is useful, but it can miss important evidence when the question has multiple intents.
For example, the question, "Can staff paste invoice data into ChatGPT?" is not only about
ChatGPT. It is also about invoice data, confidential data, approved systems, and public AI
policy.

In this project, I added a lightweight agentic workflow before answer generation. The
system checks the question, plans retrieval queries, performs multi-query vector search,
deduplicates chunks, checks whether the sources are good enough, then synthesizes the final
answer with citations.

So the system is agentic because it has decision steps around retrieval and grounding. It
does not blindly run one search. It decides what to search for, uses multiple focused
queries, evaluates source sufficiency, and exposes the intermediate steps in the UI.

I intentionally made the agent deterministic instead of using an LLM to plan the retrieval.
This makes it cheaper, easier to test, and safer for SOP workflows where we want
explainability.

## 4:15 - 5:45 Implementation Flow

Let me explain the implementation flow from documents to answer.

The first step is **document ingestion**. The backend loads markdown files from the
`data/sentral_ops` folder. Each document is split into deterministic chunks. The chunking
logic keeps chunks at a reasonable size and uses overlap so that important context is not
lost between chunks.

The second step is **embedding**. Each chunk is embedded using the configured OpenAI
embedding model.

The third step is **storage**. The vectors and metadata are stored in Qdrant. Each chunk
stores a document ID, title, chunk ID, and the chunk text.

The fourth step happens when the user asks a question. The backend does a boundary check
first. For example, it detects questions about live delivery status, payment confirmation,
stock availability, approval authority, confidential data, public AI tools, and product
substitution.

The fifth step is query planning. The system starts with the original user question. Then,
based on keywords and boundary categories, it adds focused domain-specific retrieval
queries.

The sixth step is retrieval. The system embeds all planned queries in one batch, searches
Qdrant for each query, deduplicates repeated chunks, and keeps the best score for each
chunk.

The seventh step is the grounding check. If no retrieved chunk passes the relevance
threshold, the assistant refuses to answer as company policy.

The final step is answer synthesis. Only approved source excerpts are sent to the LLM, and
the answer is instructed to cite source IDs such as `[S1]` and `[S2]`.

## 5:45 - 6:30 Demo Setup

Now I will show the working prototype.

The application is running locally with Docker Compose. The frontend is available at
`http://localhost:5173`, the backend is available at `http://localhost:8000`, and Qdrant is
running on port `6333`.

Before using the system, I can check the health endpoint to confirm the backend is ready
and that OpenAI is configured. I can also call the ready endpoint to confirm that Qdrant is
available.

[Demo action: briefly show the browser at `http://localhost:5173`.]

On the screen, you can see the main question box, the answer area, system status, and demo
questions.

## 6:30 - 8:30 Demo 1: Normal SOP Question

For the first demo, I will ask a normal SOP question:

**"What is the refund approval process for damaged goods?"**

[Demo action: submit the question.]

The assistant returns an answer based on the approved refund and credit note SOP. The
important part is that the answer is not just free text. It includes citations like `[S1]`
and matching source cards below the answer.

Here, the source cards show the document title, document ID, chunk ID, similarity score,
and the exact excerpt used by the answer. This is important because it allows a user or
evaluator to verify whether the retrieved chunks are actually relevant.

Now look at the Agent Trace. It shows the workflow:

First, the boundary check says no special warning was detected. That makes sense because
the question is about the process, not asking the assistant to approve something.

Second, the query planning step shows the original user question and a focused refund and
credit-note query. This improves retrieval recall because the system searches not only the
user wording, but also the domain vocabulary from the SOP.

Third, retrieval shows how many vector searches were run and how many candidate chunks were
deduplicated.

Fourth, the grounding check shows how many sources passed the relevance threshold.

Finally, answer synthesis confirms that the response was generated only from the cited
approved source excerpts.

This demonstrates correct chunk retrieval because the returned chunks are from the refund
SOP, and the answer is grounded in those chunks.

## 8:30 - 10:45 Demo 2: Boundary-Sensitive Question

For the second demo, I will ask a boundary-sensitive question:

**"Can staff paste invoice data into ChatGPT?"**

[Demo action: submit the question.]

This question is important because it combines multiple concerns. It mentions invoice data,
which can be confidential, and it mentions ChatGPT, which is a public AI tool.

The assistant returns warning messages. It flags confidential data and external AI usage.
This means the system is not treating the question as a simple information request. It is
recognizing the operational risk.

The answer explains that staff must not paste invoice data, customer data, payment details,
or confidential operational information into public AI tools unless management has approved
a controlled workflow.

Again, the answer includes citations. The source cards show that the system retrieved the
Data Handling and AI Usage Policy, and may also retrieve invoice handling sources. This is
the behavior I want because the correct answer requires both AI policy and invoice data
context.

The Agent Trace is especially useful here. The boundary check detected warnings. Query
planning added focused searches for invoice handling and data handling. Retrieval ran
multiple vector searches, then deduplicated the candidate chunks. The grounding check
confirmed that enough relevant chunks passed the threshold.

This is a clear example of Agentic RAG. A traditional RAG system might only search the
literal question. This system plans a broader retrieval strategy and combines evidence from
the correct SOP areas.

## 10:45 - 12:15 Demo 3: Live Operational Status Boundary

For the third demo, I will ask:

**"What is today's delivery ETA?"**

[Demo action: submit the question.]

This asks for live operational status. The assistant should not invent an ETA because the
approved SOP documents do not contain live delivery system data.

The assistant flags this as a live delivery status boundary. It can explain the SOP for
checking or escalating delivery delays, but it should tell staff to check the order system
or Operations team for the current status.

This is important because RAG should not be used to answer questions that require live data
unless it is connected to that live tool. Here, the assistant correctly separates policy
knowledge from real-time operational facts.

The Agent Trace still shows useful retrieval behavior. The planner adds a focused delivery
delay escalation query, retrieves relevant chunks, and then the answer explains the policy
boundary.

## 12:15 - 13:30 Demo 4: Out-Of-Scope Or Weak Evidence

For the fourth demo, I can ask a question that is not covered by the approved SOPs.

For example:

**"What is the company's latest marketing campaign budget?"**

[Demo action: submit an out-of-scope question.]

If no retrieved source passes the minimum source score, the assistant returns an
outside-scope warning. It says that it could not find a sufficiently relevant approved
Sentral Ops source and that staff should check the correct internal owner or specialist
team before acting.

This is a key quality behavior. The assistant does not force an answer when evidence is
weak. The grounding check protects the user from unsupported claims.

## 13:30 - 15:00 Traditional RAG Versus Agentic RAG

Now I will summarize the difference between traditional RAG and Agentic RAG.

Traditional RAG is usually a linear pipeline. It embeds the question, retrieves top-k
chunks, puts them into a prompt, and asks the LLM to answer.

Agentic RAG adds control and decision-making around that pipeline. It can plan retrieval,
choose different search strategies, call multiple tools, check whether retrieved evidence
is sufficient, and decide whether to answer or refuse.

In this implementation, the agentic behavior is intentionally focused on retrieval quality.
The system does not just retrieve once. It creates a retrieval plan, runs up to three vector
searches, deduplicates chunks, ranks them by score, filters weak chunks, and then produces a
cited answer.

This is valuable because real staff questions often contain multiple intents. A question
can be about invoices, public AI, confidential data, and policy all at the same time. A
single query may not retrieve the complete evidence. Multi-query retrieval gives the system
a better chance of retrieving the correct chunks.

Another difference is transparency. The frontend shows the Agent Trace, which helps the
user understand why the system answered the way it did. This is useful for debugging,
evaluation, and stakeholder trust.

## 15:00 - 16:30 Retrieval Optimization

There are several retrieval optimization choices in this project.

First, chunks are deterministic. The same document produces stable chunk IDs, so sources
are traceable and testable.

Second, chunks use overlap. This reduces the chance that a section boundary splits
important context away from the answer.

Third, the query planner adds domain-specific search queries. For example, refund questions
get refund and credit-note terms. Delivery questions get delivery delay and escalation
terms. Public AI questions get data handling and confidential-data terms.

Fourth, duplicate chunks are removed. If the same chunk appears from multiple searches, the
system keeps one copy with the best score. This prevents the prompt from being filled with
repeated evidence.

Fifth, the source threshold protects grounding. The `MIN_SOURCE_SCORE` setting controls
how confident retrieval must be before the LLM receives context. If the threshold is not
met, the assistant refuses to answer as policy.

Sixth, `MAX_CONTEXT_SOURCES` limits the number of chunks sent to the LLM. This keeps the
prompt focused and helps performance.

## 16:30 - 18:00 Testing Methodology

The backend test suite focuses on the parts that matter most for quality.

There are chunking tests. These verify that chunk IDs are deterministic, that chunk sizes
stay reasonable, and that invalid chunking settings are rejected.

There are guardrail tests. These check whether the system detects public AI and
confidential data, payment confirmation, live delivery ETA, approval authority, product
substitution, and normal SOP questions that should not trigger false warnings.

There are Agentic RAG tests. These verify that the retrieval planner adds the correct
domain-specific queries, that boundary warnings can trigger focused retrieval, that
duplicate chunks are merged correctly, that source threshold filtering works, and that
citations are assigned in rank order.

I also run the frontend TypeScript build. This verifies that the frontend schema matches
the backend response shape, including `agent_steps` and source `citation` fields.

For manual testing, I use demo questions that cover normal SOP answers, boundary-sensitive
answers, and out-of-scope refusal. During the demo, I inspect the source snippets and Agent
Trace to verify that the answer is grounded in the correct documents.

## 18:00 - 19:15 Limitations And Production Considerations

This is a working prototype, but there are still production considerations.

First, the system does not include authentication or role-based access control. A real
company deployment would need user login and permissions.

Second, it does not include audit logging. In production, I would log questions, answers,
retrieved sources, warnings, and user identity for compliance and debugging.

Third, the prototype uses fictional SOP data. Real company data would require a document
approval workflow, data classification, and re-ingestion process.

Fourth, stronger security testing would be needed for prompt injection and data
exfiltration attempts.

Fifth, if the assistant needs live delivery status, payment confirmation, or stock
availability, it should be connected to approved operational systems as tools. Without
those tools, it should continue to explain only the SOP and tell staff where to check live
data.

## 19:15 - 20:00 Closing

To conclude, this project satisfies the assessment requirement for Question 1.

It is a working Agentic RAG prototype with a React frontend, FastAPI backend, Qdrant vector
database, OpenAI embeddings and answer generation, Docker deployment, citations, source
snippets, and an inspectable Agent Trace.

The key contribution is that the system does not only perform basic RAG. It uses an
agentic retrieval workflow: boundary check, query planning, multi-query retrieval,
deduplication, grounding check, and cited answer synthesis.

This makes the assistant more reliable for internal SOP use because it retrieves better
evidence, avoids weakly grounded answers, warns about sensitive operational boundaries, and
shows the user exactly which sources were used.

That completes my presentation. Thank you.

## Short Backup Script If You Need To Finish Faster

If you are running out of time, say this:

This prototype implements Agentic RAG for a private SOP assistant. Traditional RAG embeds
the question once, retrieves top-k chunks, and generates an answer. My system adds an
agentic workflow before generation. It checks boundaries, plans focused retrieval queries,
runs multi-query vector search in Qdrant, deduplicates chunks, filters weak sources using a
minimum score threshold, assigns citations, and only then asks the LLM to synthesize an
answer from approved excerpts.

The frontend demonstrates the answer, warnings, citations, source snippets, and Agent
Trace. The tests cover chunking, guardrails, retrieval planning, deduplication, source
filtering, and citation labels. The application also runs with Docker Compose, which covers
the deployment bonus point.
