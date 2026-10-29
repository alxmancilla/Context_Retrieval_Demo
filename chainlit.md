# Try the MongoDB-backed context assistant

Click a **sample question** below to show how MongoDB helps the customer move from slow
multi-agent answer merging to fast, governed evidence retrieval.

This demo does not call answer-generating subagents. The LangGraph coordinator calls thin,
source-scoped retrieval tools that return evidence only, then generates one final cited answer.

The assistant uses MongoDB Atlas as the operational retrieval plane: source metadata, Atlas Search,
Vector Search, rank fusion, checkpoints, semantic memory, and evidence audit trails. It routes
sources, retrieves evidence in parallel, reconciles conflicts, and generates one cited answer.

**Recommended demo flow**

1. Start with **Rx auth current state** or **Eligibility cache timeline** to test the original
   healthcare corpus with real source conflicts, stale evidence, and citations.
2. Try **GitHub + Jira auth proof** or **GitHub + Jira + Teams PA events** to show
   targeted 2-source and 3-source routing in the Pipeline Trace.
3. Try **Merge evidence, not answers** to show the MongoDB retrieval advantage.
4. Finish with **Executive value summary** for a customer-ready MongoDB value story.

Use the **Architecture** link in the header when you want the visual solution diagram.
