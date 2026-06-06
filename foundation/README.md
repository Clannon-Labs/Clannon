# foundation/

The `foundation` package defines the shared vocabulary and transport layer for
Vraksha. Every other layer may import from here. This package must not import
from the rest of the codebase.

If you are new to the project, start here. If you are tracing where a type,
status, error, or constant comes from, it should usually be defined or exported
by this package.

## What Lives Here

```
foundation/
  __init__.py
    Public import surface for the foundation package.

  constants.py
    Hardcoded values such as timeouts, limits, and thresholds.

  flow.py
    Flow, the primary transport for stage handoffs.

  model_registry.py
    Root models.yaml loader and cached model profile resolver.

  pillars/
    __init__.py
      Public import surface for foundation primitives.

    context.py
      VrakshaContext, the request-scoped state object.

    errors.py
      Exception classes, organized by layer.

    transport.py
      Envelope and Meta, the low-level primitives Flow uses.

    types.py
      Shared primitive enums such as Modality, ThreatLevel, and Origin.
```

The pillar modules are the primitive layer. They do not import from the rest of
Vraksha. `flow.py` builds on those primitives, and `foundation/__init__.py`
re-exports the public names that application code should use.

## Import Rule

Import public names from the package, not from individual files:

```python
# correct
from foundation import Flow, Origin, VrakshaContext, Modality

# wrong: bypasses __init__.py and breaks if files are reorganized
from foundation.flow import Flow
from foundation.context import VrakshaContext
```

Constants are the main exception. Import the module so the call site clearly
shows where the value comes from:

```python
# correct
from foundation import constants
timeout = constants.VERIFIER_TIMEOUT_S

# wrong: bare name with no context
from foundation.constants import VERIFIER_TIMEOUT_S
```

Model routing is also exposed through the package:

```python
from foundation import load_model_registry

model = load_model_registry().for_layer("orchestrator")
```

## flow.py: Flow

Start here. `Flow` is the primary transport. Every stage takes a `Flow` and
returns a `Flow`. It carries the payload, context, trace metadata, journal, and
state transition logic in one object.

Design lineage:
- Railway Oriented Programming: automatic error propagation through `.then()`.
- OpenTelemetry Baggage: controlled access with trace metadata always present.
- Google ADK Handle pattern: payloads are lazy references, not inline data.
- Transition journal: every state change is recorded automatically.

**The stage import:**

```python
from foundation import Flow
```

**Create once, in `pipeline.py`:**

```python
flow = Flow.new(raw_input, session_id=session.id)
```

**Write a stage with this pattern:**

```python
async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    try:
        raw = await flow.load()              # load payload only when needed
        result = await do_work(raw)
        return flow.next(result, Origin.SANITIZER, started)
    except SanitizationError as e:
        return flow.fail(e, Origin.SANITIZER, started)
```

**Block when the pipeline must stop:**

```python
return flow.block(BlockReason.MALICIOUS_CONTENT, ThreatLevel.HIGH, Origin.SANITIZER)
```

**Warn when the pipeline may continue with a flag:**

```python
return flow.warn("low confidence score", ThreatLevel.LOW, Origin.VERIFIER, started)
```

**Fail for infrastructure or code faults, not threats:**

```python
except ModelUnavailableError as e:
    return flow.fail(e, Origin.VERIFIER, started)
```

**Check status through properties:**

```python
if flow.ok:          ...   # Status.OK
if flow.blocked:     ...   # Status.BLOCKED
if flow.warned:      ...   # Status.WARN
if flow.errored:     ...   # Status.ERROR
if flow.should_stop: ...   # BLOCKED or ERROR, checked automatically by .then()
```

**Chain stages in Railway style:**

```python
# preferred: declarative pipeline, no manual control flow
result = await Flow.chain(
    Flow.new(raw_input, session_id),
    [
        intake.process,
        sanitizer.run,
        normalizer.run,
        verifier.verify,
        orchestrator.run,
        output_filter.run,
        output.send,
    ]
)

# manual: use when you need fine control between stages
flow = await sanitizer.run(flow)
if flow.should_stop:
    return flow
```

**Load payloads explicitly:**

```python
# flow.load() triggers the loader once and caches the result
# calling load() twice is safe and free
raw = await flow.load()

# after flow.next(), the old payload is offloaded automatically
# GC can free large data such as PDF bytes or audio buffers
```

**Use the right observability method:**

```python
# summary(): structured logging in every stage
# safe: never includes raw payload, PII, or sensitive content
logger.warning("flow blocked", **flow.summary())

# audit(): dead letter output and post-mortem debugging
# full journal of every state transition as a list of dicts
dead_letter_writer.write(flow.audit())

# replay(): development debugging only
# human-readable journey through the pipeline
print(flow.replay())
# Output:
# Flow abc12345... journey:
#   00. [OK      ] intake               -
#   01. [OK      ] sanitizer         12.3ms
#   02. [BLOCKED ] verifier           4.1ms  verifier_rejected
```

**Never log the full flow object:**

```python
# correct
logger.warning("blocked", **flow.summary())

# wrong: journal and payload descriptor may contain sensitive details
logger.warning("blocked", flow=flow)
```

**Access context through `flow.ctx`:**

```python
# read session state
session_id = flow.ctx.session_id

# write stage results back
flow.ctx.sanitization = result
flow.ctx.detected_modalities = result.modalities

# append tool/expert call records
flow.ctx.tool_calls.append(ToolCallRecord(tool_name="search", arguments={...}))
```

## Using Flow Across Layers

For a full architecture walkthrough, see **[FLOW_GUIDE.md](https://github.com/vraksha/vraksha/blob/refractor/foundation/FLOW_GUIDE.md)**.

That guide shows how `Flow` should move through sanitizers, normalization,
verification, the Pydantic AI orchestrator, tool and expert handlers, output
filtering, output delivery, and memory writes. It also covers how to add a new
layer without breaking the Flow contract.

## transport.py: Envelope and Meta

`Envelope` and `Meta` are the low-level primitives that `Flow` uses.

Most stage code should use `Flow` instead. Use `Envelope` directly only when
you need low-level control outside the standard pipeline, such as internal
worker-to-worker communication inside the sanitizer runner before results are
joined.

`Origin` used to live in `transport.py`. It now lives in `types.py`. Import it
with:

```python
from foundation import Origin
```

## errors.py: Error Taxonomy

Exceptions are organized by layer. A traceback should tell you which layer
failed before you read the detailed message.

```
1xx InputError          : the user input caused the problem
2xx SecurityError       : a threat was detected, or the security layer failed
3xx OrchestratorError   : the reasoning loop or an invocation failed
4xx InfrastructureError : a dependency, model, sandbox, or memory store failed
```

**Raise specific errors, never bare `Exception`:**

```python
from foundation import SanitizationError, ModelUnavailableError, CircuitOpenError

# carry trace_id so logs correlate
raise SanitizationError(
    "embedded JS in PDF stream",
    trace_id=flow.meta.trace_id,
    modality="pdf",
    worker="pikepdf",
)

# wrap the original exception, never swallow it
try:
    response = await llm_client.complete(...)
except httpx.TimeoutException as e:
    raise ModelUnavailableError(
        "verifier timed out after 8s",
        trace_id=flow.meta.trace_id,
        cause=e,
        model="verifier",
    )
```

**Convert exceptions at stage boundaries:**

Exceptions must not cross stage boundaries. Convert them into `Flow`
transitions at the edge:

```python
async def run(flow: Flow) -> Flow:
    try:
        result = await call_verifier(await flow.load())
        return flow.next(result, Origin.VERIFIER, started)
    except VerifierError as e:
        return flow.block(BlockReason.VERIFIER_REJECTED, ThreatLevel.HIGH, Origin.VERIFIER, started)
    except ModelUnavailableError as e:
        return flow.fail(e, Origin.VERIFIER, started)
```

**Use the fields on specific errors:**

```python
# SanitizationError carries modality and worker
except SanitizationError as e:
    logger.warning("sanitizer blocked", modality=e.modality, worker=e.worker)

# CircuitOpenError carries service and retry_after
except CircuitOpenError as e:
    logger.error("circuit open", service=e.service, retry_after=e.retry_after)

# ToolError carries tool name
except ToolError as e:
    logger.error("tool failed", tool=e.tool)
```

## model_registry.py: Model Routing

`model_registry.py` is the single foundation-level bridge to root model
configuration. LLM-using layers should resolve providers and model names through
this registry instead of hardcoding them.

It reads `models.yaml`, caches the parsed registry, and supports optional
role/layer routes such as `orchestrator`, `verifier`, `normalizer`, `filter`,
and `media_expert`.

```python
from foundation import load_model_registry

registry = load_model_registry()
profile = registry.for_layer("orchestrator")

if profile.supports("image"):
    ...
```

`load_model_registry()` is cached for hot-path performance. Test or config
reload code can call:

```python
load_model_registry.cache_clear()
```

The optional `VRAKSHA_MODEL_PROVIDER` environment variable can override the
default provider. That override belongs here because model routing is owned by
the registry.

## constants.py: Hardcoded Values

No magic number or magic string should live elsewhere in the codebase. If you
find one, move it here.

**Read constants through the module:**

```python
from foundation import constants

# timeouts
async with asyncio.timeout(constants.VERIFIER_TIMEOUT_S):
    result = await verifier.run(flow)

# size limits
if len(raw_text) > constants.MAX_TEXT_INPUT_CHARS:
    raise InputTooLargeError(...)

# circuit breaker thresholds
if failure_count >= constants.CB_FAILURE_THRESHOLD:
    trip_circuit()
```

**Add a new constant this way:**

1. Find the right section, such as PIPELINE, INTAKE, SANITIZERS, or VERIFIER.
2. Add it with a type-appropriate name in `SCREAMING_SNAKE_CASE`.
3. Add an inline comment explaining what triggers or uses it.
4. For timeouts, suffix the name with `_S` for seconds or `_MS` for milliseconds.
5. For byte sizes, write `N * 1024 * 1024` instead of a raw integer.

**Do not:**
- Import individual constants by name. Always import the module.
- Set constants from environment variables here. That belongs in `config/settings.py`.
- Add business logic here. This file is for values only.

## context.py: VrakshaContext

`VrakshaContext` is the single source of truth for one user turn. `Flow.new()`
creates it automatically and stores it on `flow.ctx`. Stage code should not
instantiate it directly.

**Access context in a stage:**

```python
# always via flow.ctx
session_id = flow.ctx.session_id
modalities = flow.ctx.detected_modalities
```

**Write stage results only to fields owned by that stage:**

```python
flow.ctx.sanitization = result           # written by sanitizer
flow.ctx.verifier_result = result        # written by verifier
flow.ctx.orchestrator_response = result  # written by orchestrator
```

**Let Flow manage terminal state:**

```python
# Flow.block() calls ctx.mark_blocked() automatically
# Flow.fail()  calls ctx.mark_failed()  automatically
# Flow.new()   sets the initial INTAKE stage
#
# Flow.next() and Flow.warn() do not advance ctx.current_stage.
# Stages that want current_stage accuracy should call ctx.advance().
# Use Flow.meta.origin and flow.audit() for transition history.
```

**Log with `snapshot()`:**

```python
# correct: excludes raw_input and other sensitive payload fields
logger.error("pipeline failed", **flow.ctx.snapshot())

# wrong: raw_input may contain the malicious payload itself
logger.error("pipeline failed", ctx=flow.ctx)
```

**Replace placeholder fields as layers are built:**

Several fields are typed as `Any | None` with `# PLACEHOLDER` comments. When
you build the corresponding layer, replace `Any` with the real type:

```python
# before
sanitization: Any | None = None  # PLACEHOLDER: will be sanitizers.SanitizationResult

# after: once security/sanitizers/schema.py exists
from security.sanitizers.schema import SanitizationResult
sanitization: SanitizationResult | None = None
```

Do not remove the comment. Update it to say what replaced the placeholder.

## types.py: Shared Primitives

This file contains enums that multiple layers use independently. If you would
otherwise define the same enum in two different layers, it belongs here.

`Origin`, which identifies the stage that produced a `Flow` or `Envelope`, lives
in `types.py`, not in `transport.py`.

```python
from foundation import Modality, ThreatLevel, BlockReason, Origin, PermissionLevel

# intake detects modalities
flow.ctx.detected_modalities = [Modality.TEXT, Modality.PDF]

# sanitizers report threat level
if threat_level.should_block:
    return flow.block(BlockReason.MALICIOUS_CONTENT, ThreatLevel.HIGH, Origin.SANITIZER)

# registry enforces permission level
if tool.required_permission > expert.granted_permission:
    raise ToolNotPermittedError(...)

# orchestrator checks expert state before invoking
if expert.state != ExpertState.AVAILABLE:
    raise ExpertError("expert not available", expert=expert.name)
```

**Add a new enum only when it is shared:**

Only add an enum to `types.py` if two or more unrelated layers use it. If the
enum belongs to one layer, such as `security/`, define it in that layer's own
`schema.py` instead.

## Editing This Package

**Safe changes:**
- Change constant values in `constants.py`.
- Update docstrings and comments while keeping them accurate.
- Add new error classes to `errors.py` if they follow the taxonomy and are exported.
- Add new enum values to `types.py`.
- Add new fields to `VrakshaContext`; use `# PLACEHOLDER` if the type is not ready.

**Changes that require care:**
- Rename anything exported from `__init__.py`; it is imported throughout the project.
- Change `Flow` method signatures; every stage in the pipeline uses them.
- Change `Meta` field names; both `Flow` and `Envelope` reference them.
- Remove enum values from `types.py`; check all usages first.
- Change `VrakshaContext` field names; stages reference them through `flow.ctx`.

**Do not:**
- Import from anywhere else in Vraksha inside this package.
- Add business logic or LLM calls to any file here.
- Add I/O here except for foundation-owned configuration loading such as
  `model_registry.py`.
- Define layer-specific types here; they belong in that layer's `schema.py`.
- Read environment variables here, except for foundation-owned routing overrides
  such as `VRAKSHA_MODEL_PROVIDER` in `model_registry.py`.
- Call `ctx.mark_blocked()` or `ctx.mark_failed()` directly in stage code. Use
  `flow.block()` or `flow.fail()` instead.

## Dependency Rule

```
everything else
      |
      v
  foundation/
      |
      v
  (nothing)
```

This direction must never be reversed. If you want to import from `core/`,
`security/`, or any other layer inside `foundation/`, the type probably lives in
the wrong place. Move it to the layer that owns it, or extract a primitive into
`types.py` if it is genuinely shared.
