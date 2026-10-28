# How can I help with your enterprise context?

Ask a natural-language question across simulated **GitHub, Confluence, Jira, SharePoint, and Teams**.

The coordinator searches source specialists in parallel, uses Voyage AI to rerank authorized
evidence, and combines semantic relevance, governed authority, and freshness. When sources
conflict, it identifies one current or authoritative representative per value, distinguishes
historical suggestions from effective policy, and reports the score margin.

Every factual citation is bound to a retrieved artifact. Expand **Agent activity** only when you
want the details: Atlas scores, Voyage rerank scores, governance, contradiction representatives,
lifecycle status, and the final deterministic decision.

Embeddings are managed by Atlas Automated Embedding indexes over the `content` field, so you will
not see `embedding` arrays in the collections. Source retrieval combines Atlas Vector Search,
lexical Search, ACL filters, and `$rankFusion`; Voyage reranks only authorized candidates. The
retrieval inspector also shows the active source routing mode: `intent`, `all`, or `explicit_only`.

## Visual architecture

[![Open the solution architecture diagram](/public/solution-architecture.png)](/public/solution-architecture.png)

Use the preview above, or the **Architecture** link in the header, to open the visual design
diagram only when you want it.
