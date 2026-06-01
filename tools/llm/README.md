# LLM Primitive

Purpose: perform model-backed generation, summarization, transformation, and
extraction as a brokered capability.

Planned capability names:

* `llm_generate`
* `llm_summarize`
* `llm_extract`

Current registry entry:

* `tool.llm.generate`

Current behavior:

* validates `prompt`, `purpose`, and output-size intent
* fails closed until model policy and provider routing are implemented

Budgets, model selection, prompt boundaries, and data handling rules belong at
the broker/policy boundary.
