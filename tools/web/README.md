# Web Primitive

Purpose: search and fetch web content through controlled broker requests.

Planned capability names:

* `web_search`
* `web_fetch`

Current registry entry:

* `tool.web.fetch`

Current behavior:

* validates HTTP/HTTPS URL input
* fails closed until network policy and source controls are implemented

Network access should be policy-gated, rate-limited, and source-aware before
this primitive executes.
