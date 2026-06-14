# Flow Guide

This guide shows how `Flow` should move through Vraksha's architecture. It is
not a full implementation. It is the shape to copy when building real layers.

The rule from `foundation/flow.py` is the source of truth:

```text
Every stage boundary takes a Flow and returns a Flow.
Nothing else crosses stage boundaries.
```

That means the pipeline does not pass raw strings, dicts, model objects, tool
results, or expert responses directly between layers. Those values move inside
the current `Flow` payload or through clearly owned fields on `flow.ctx`.

## High-Level Pipeline

```python
from foundation import Flow


async def run_pipeline(raw_input: object, session_id: str) -> Flow:
    return await Flow.chain(
        Flow.new(raw_input, session_id=session_id),
        [
            intake.process,
            sanitizer.run,
            normalizer.run,
            verifier.run,
            orchestrator.run,
            output_filter.run,
            output.run,
        ],
    )
```

Each function in that list has the same public shape:

```python
async def run(flow: Flow) -> Flow:
    ...
```

If a stage blocks or fails, `Flow.chain()` skips the remaining stages
automatically because `flow.should_stop` becomes true.
Warnings do not stop the chain. A WARN flow still reaches the next stage with
`flow.warned`, `flow.reason`, and `flow.threat` available.

`Flow.chain()` is for straight-line execution. If a stage can send work back to
an earlier stage, such as the output filter asking the orchestrator to revise,
use an explicit loop in `core/pipeline.py`.

## Payload Versus Context

Use the payload for what the next stage should process.

Use `flow.ctx` for request-scoped state that later stages may inspect.
Use `Flow.meta.origin` and `flow.audit()` for the transition history. `Flow`
does not advance `flow.ctx.current_stage` on every `flow.next()` or
`flow.warn()` call, so stages that care about live stage accuracy should call
`flow.ctx.advance(...)` explicitly.

Example:

```python
sanitized = await sanitize(payload)

flow.ctx.sanitization = sanitized.report
flow.ctx.detected_modalities = sanitized.modalities

return flow.next(sanitized.content, Origin.SANITIZER, started)
```

In this example, `sanitized.content` becomes the next payload. The report and
modalities stay on the context for observability and later decisions.

## Intake

Intake receives the raw user input and records basic request state. It should
not do deep security analysis. That belongs to the sanitizer workers.

Current intake also performs cheap admission checks before expensive work:

- per-session and global request rate limiting
- raw input size limits
- MIME/modality detection

```python
from foundation import BlockReason, Flow, Origin, PipelineStage, ThreatLevel


async def process(flow: Flow) -> Flow:
    started = time.monotonic()
    raw_input = await flow.load()

    if not check_request_rate(flow.ctx.session_id).allowed:
        return flow.block(BlockReason.RATE_LIMITED, ThreatLevel.NONE, Origin.INTAKE, started)

    if input_is_too_large(raw_input):
        return flow.block(BlockReason.INPUT_TOO_LARGE, ThreatLevel.NONE, Origin.INTAKE, started)

    detected = detect_modalities(raw_input)

    flow.ctx.raw_input = raw_input
    flow.ctx.detected_modalities = [m.value for m in detected]
    flow.ctx.advance(PipelineStage.INTAKE)

    return flow.next(raw_input, Origin.INTAKE, started)
```

## Sanitization With Parallel Workers

Sanitization is the first security boundary. It should inspect every modality
present in the input: text, PDF, image, audio, video, and anything else the
intake layer recognizes.

The sanitizer runner may fan out internally, but the outside contract stays the
same: one `Flow` in, one `Flow` out.

```python
from foundation import (
    BlockReason,
    Flow,
    Origin,
    PipelineStage,
    SanitizationError,
    ThreatLevel,
)


async def run(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw_input = await flow.load()
        flow.ctx.advance(PipelineStage.SANITIZING)

        pre_result = await pre_sanitization.run(raw_input)
        if pre_result.threat_level.should_block:
            flow.ctx.sanitization = pre_result
            flow.ctx.sanitization_blocked = True
            flow.ctx.sanitization_block_reason = pre_result.reason
            return flow.block(BlockReason.MALICIOUS_CONTENT, pre_result.threat_level, Origin.SANITIZER, started)

        results = await run_workers_for_modalities(raw_input, flow.ctx.detected_modalities)

        flow.ctx.sanitization = results.report

        if results.blocked:
            flow.ctx.sanitization_blocked = True
            flow.ctx.sanitization_block_reason = results.reason
            return flow.block(
                BlockReason.MALICIOUS_CONTENT,
                results.threat_level or ThreatLevel.HIGH,
                Origin.SANITIZER,
                started,
            )

        return flow.next(results.safe_content, Origin.SANITIZER, started)

    except SanitizationError as e:
        return flow.fail(e, Origin.SANITIZER, started)
```

When sanitization blocks, the user response should be generated by the system,
not by an LLM. For example: "Your input was blocked because it failed the
safety checks." Keep the exact internal reason in logs or dead letter output,
not in the user-facing message.

## Normalization

Normalization should convert sanitized input into a structured form. It is
code-only in the current implementation: it does not call an LLM.

The current `NormalizedInput` is a dataclass with:

- `modality`
- `content_type`
- `content`
- `native_payload`
- `target_layer`
- `target_provider`
- `target_model`
- `preserved_native`
- `requires_expert`
- `required_capability`
- `metadata`

Then the stage writes it to context and passes it forward:

```python
from foundation import Flow, Origin, PipelineStage


async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    sanitized_content = await flow.load()

    modality = flow.ctx.detected_modalities[0] if flow.ctx.detected_modalities else "text"
    normalized = normalize_payload(sanitized_content, modality=modality)

    flow.ctx.normalized_input = normalized
    flow.ctx.advance(PipelineStage.NORMALIZING)
    return flow.next(normalized, Origin.NORMALIZER, started)
```

### Should Everything Become Text?

No. Do not nerf the agent by forcing all input into text.

Use a structured normalized representation as the pipeline payload. Text can be
one field inside that structure, but native or near-native references should
remain available when the model or a tool can use them safely.

The practical rule is:

1. Sanitize native input first.
2. Extract text, metadata, and safe summaries for security checks.
3. Preserve safe references to native artifacts when they are useful.
4. Give each LLM only the representation it needs for its job.

The verifier probably does not need full native files. It should usually see a
compact structured view with extracted text, modality metadata, sanitizer
findings, and attachment descriptors.

The orchestrator can receive richer structured data after verification. If the
target model supports the native modality, the normalizer can preserve the
sanitized native payload. If it does not, the normalized object marks
`requires_expert=True` and records the required media capability for later
routing to a capable expert/model.

## Verification

The verifier is a fast LLM with a narrow job. It should classify the sanitized,
normalized input and return predefined structured output only.

With Pydantic AI, model that output as a schema:

```python
from pydantic import BaseModel
from foundation import BlockReason, Flow, Origin, ThreatLevel, VerifierError


class VerificationResult(BaseModel):
    dangerous: bool
    warn: bool
    proceed: bool
    threat_level: str
    reason: str | None = None


async def run(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        normalized = await flow.load()
        result = await verifier_agent.run(normalized)

        flow.ctx.verifier_result = result.output

        if result.output.dangerous or not result.output.proceed:
            flow.ctx.verifier_blocked = True
            flow.ctx.verifier_block_reason = result.output.reason
            return flow.block(
                BlockReason.VERIFIER_REJECTED,
                ThreatLevel.HIGH,
                Origin.VERIFIER,
                started,
            )

        if result.output.warn:
            flow.ctx.verifier_block_reason = result.output.reason
            return flow.warn(
                result.output.reason or "verifier warning",
                ThreatLevel.LOW,
                Origin.VERIFIER,
                started,
            )

        return flow.next(normalized, Origin.VERIFIER, started)

    except VerifierError as e:
        return flow.fail(e, Origin.VERIFIER, started)
```

The verifier should not produce free-form user-facing text. Its output should be
machine-readable and schema-validated.

## Orchestrator

The orchestrator is the main Pydantic AI agent. It has the highest-level context
and controlled access to memory, tools, and experts.

It should still follow the Flow contract:

```python
from foundation import Flow, ModelUnavailableError, Origin


async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    payload = await flow.load()

    try:
        if flow.ctx.filter_result and flow.ctx.filter_result.retry:
            prompt = build_revision_prompt(
                original_input=flow.ctx.normalized_input,
                previous_response=flow.ctx.orchestrator_response,
                filter_result=flow.ctx.filter_result,
            )
        else:
            prompt = build_orchestrator_prompt(
                normalized_input=payload,
                memory_context=await memory.read_relevant(
                    session_id=flow.ctx.session_id,
                    query=payload,
                ),
            )

        result = await orchestrator_agent.run(
            user_prompt=prompt,
            deps=OrchestratorDeps(
                trace_id=flow.meta.trace_id,
                tool_handler=tool_handler.invoke,
                expert_handler=expert_handler.invoke,
                expert_registry=expert_registry.snapshot(),
            ),
        )

        flow.ctx.orchestrator_response = result.output
        flow.ctx.memory_writes_requested = result.output.memory_write_requests

        return flow.next(result.output, Origin.ORCHESTRATOR, started)

    except ModelUnavailableError as e:
        return flow.fail(e, Origin.ORCHESTRATOR, started)
```

The orchestrator may ask handlers to invoke tools or experts, but handlers
should own the actual execution boundary. The orchestrator should not directly
run shell commands, write files, or call expert internals.

## Tool Handler

Tool calls are part of an orchestrator turn, not separate top-level pipeline
stages. The handler should still record what happened on `flow.ctx` through a
record created by the orchestrator-side dependency.

The tool handler should:

1. Validate the requested tool exists.
2. Check permissions.
3. Sanitize and validate arguments.
4. Execute inside the sandbox.
5. Return structured JSON with `success: bool`.
6. Append a `ToolCallRecord` to `flow.ctx.tool_calls`.

Shape:

```python
from foundation import Flow, ToolCallRecord


async def invoke_tool(flow: Flow, request: ToolRequest) -> ToolResult:
    started = time.monotonic()

    result = await sandbox.run_tool(
        name=request.tool_name,
        arguments=request.arguments,
    )

    flow.ctx.tool_calls.append(
        ToolCallRecord(
            tool_name=request.tool_name,
            arguments=request.arguments,
            result=result.data if result.success else None,
            success=result.success,
            duration_ms=elapsed_ms(started),
            error=result.error,
            span_id=flow.meta.span_id,
        )
    )

    return ToolResult(success=result.success, data=result.data, error=result.error)
```

The result that returns to the orchestrator should be structured, not arbitrary
free text.

## Expert Handler

Experts are sub-agents with their own prompts, skills, and limited permissions.
They may know what tools and experts exist, but they should only use what they
are allowed to use.

The expert handler should:

1. Check the expert state and capability profile.
2. Validate the request from the orchestrator.
3. Enforce the expert's allowed tools and expert contacts.
4. Invoke the expert with scoped dependencies.
5. Record the call in `flow.ctx.expert_calls`.
6. Return structured output to the orchestrator.

```python
from foundation import ExpertCallRecord, Flow


async def invoke_expert(flow: Flow, request: ExpertRequest) -> ExpertResult:
    started = time.monotonic()

    expert = expert_registry.get(request.expert_name)
    permissions.enforce_expert_access(expert, request)

    result = await expert.agent.run(
        user_prompt=request.prompt,
        deps=ExpertDeps(
            allowed_tools=expert.allowed_tools,
            allowed_experts=expert.allowed_experts,
            grant_requester=orchestrator_permission_gate,
        ),
    )

    flow.ctx.expert_calls.append(
        ExpertCallRecord(
            expert_name=request.expert_name,
            arguments=request.arguments,
            result=result.output if result.success else None,
            success=result.success,
            duration_ms=elapsed_ms(started),
            error=result.error,
            span_id=flow.meta.span_id,
        )
    )

    return ExpertResult(success=result.success, data=result.output, error=result.error)
```

Experts can request more tools. The orchestrator should decide whether the
request is reasonable, ask the user when elevated access is required, and grant
temporary access only for the current task.

Expert-to-expert communication does not need user approval by default, but it
must remain visible to the orchestrator. The orchestrator or handler can block
or warn if an expert tries to pass unsafe data or contact a disallowed expert.

## Output Handler and Filter

The output handler turns the orchestrator response into the candidate user
response. The filter then checks both the original user context and the
candidate output.

The filter is another fast structured-output LLM, similar to the verifier:

```python
from pydantic import BaseModel


class FilterResult(BaseModel):
    accepted: bool
    retry: bool
    reason: str | None = None
    sanitized_output: str | None = None
```

The stage can either pass the output forward, block it, or mark that a retry is
needed. If retry is allowed, the pipeline loop calls the orchestrator again.

```python
from foundation import BlockReason, Flow, Origin, ThreatLevel, constants


async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    candidate = await flow.load()

    result = await filter_agent.run(
        {
            "input": flow.ctx.normalized_input,
            "candidate_output": candidate,
        }
    )

    flow.ctx.filter_result = result.output

    if result.output.accepted:
        output = result.output.sanitized_output or candidate
        return flow.next(output, Origin.FILTER, started)

    if result.output.retry and flow.ctx.filter_retry_count < constants.MAX_OUTPUT_RETRIES:
        flow.ctx.filter_retry_count += 1
        return flow.next(candidate, Origin.FILTER, started)

    flow.ctx.filter_blocked = True
    flow.ctx.filter_block_reason = result.output.reason
    return flow.block(BlockReason.FILTER_REJECTED, ThreatLevel.HIGH, Origin.FILTER, started)
```

If filter retry becomes a real loop, prefer making it explicit in
`core/pipeline.py` instead of hiding the loop inside a stage. `Flow.chain()` is
best for straight-line stages. Manual control is better when a stage can jump
back to the orchestrator.

Manual loop shape:

```python
from foundation import BlockReason, Flow, Origin, ThreatLevel, constants


async def run_pipeline(raw_input: object, session_id: str) -> Flow:
    flow = Flow.new(raw_input, session_id=session_id)

    for stage in [
        intake.process,
        sanitizer.run,
        normalizer.run,
        verifier.run,
    ]:
        flow = await stage(flow)
        if flow.should_stop:
            return flow

    accepted = False

    for _ in range(constants.MAX_OUTPUT_RETRIES + 1):
        flow = await orchestrator.run(flow)
        if flow.should_stop:
            return flow

        flow = await output_filter.run(flow)
        if flow.should_stop:
            return flow

        if flow.ctx.filter_result and flow.ctx.filter_result.accepted:
            accepted = True
            break

    if not accepted:
        return flow.block(
            BlockReason.MAX_RETRIES_EXCEEDED,
            ThreatLevel.HIGH,
            Origin.FILTER,
        )

    flow = await output.run(flow)
    if flow.should_stop:
        return flow

    background_tasks.create_task(memory_writer.run(flow))
    return flow
```

The exact control signal can evolve, but the boundary does not change: every
call still takes a `Flow` and returns a `Flow`.

`background_tasks` is a placeholder for your runtime's task scheduler.

## Output and Memory Writes

The output stage performs final cheap formatting and prepares the final response.
It should not call the main LLM.

```python
async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    final_response = await flow.load()

    checked = output_checks(final_response)

    flow.ctx.final_response = checked
    return flow.next(checked, Origin.OUTPUT, started)
```

Memory writes can run after the response is ready. If the user does not need to
wait for persistence, schedule the memory writer as a background task after
`output.run()` succeeds.

Memory writers should use `flow.ctx.memory_writes_requested`, not re-derive
memory from raw input.

```python
async def run(flow: Flow) -> Flow:
    started = time.monotonic()
    final_response = await flow.load()

    await memory.write_many(flow.ctx.memory_writes_requested)

    return flow.next(final_response, Origin.MEMORY, started)
```

If memory write failure should not block the user response, return
`flow.warn(...)` or record the failure separately. If memory durability is
critical for a specific operation, return `flow.fail(...)`.

## Adding a New Layer

When adding a new layer, do this:

1. Add an `Origin` value in `foundation/pillars/types.py`.
2. Add a `PipelineStage` value in `foundation/pillars/context.py` if explicit
   stage tracking is needed.
3. Add fields to `VrakshaContext` only if later stages need durable request
   state.
4. Add the stage to the pipeline chain or to the manual pipeline loop.
5. Make the stage accept `Flow` and return `Flow`.
6. Use `flow.next()`, `flow.block()`, `flow.warn()`, or `flow.fail()` for every
   exit path.

Template:

```python
from foundation import Flow, Origin, VrakshaError


async def run(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        payload = await flow.load()
        result = await do_work(payload, flow.ctx)

        flow.ctx.new_layer_result = result
        return flow.next(result, Origin.NEW_LAYER, started)

    except VrakshaError as e:
        return flow.fail(e, Origin.NEW_LAYER, started)
```

`Origin.NEW_LAYER` is a placeholder. Replace it with the real enum value you
add to `foundation/pillars/types.py`.

## What Not To Do

Do not pass raw payloads between layers:

```python
# wrong
normalized = await normalizer.run(raw_input)
verified = await verifier.run(normalized)
```

Use `Flow`:

```python
# correct
flow = await normalizer.run(flow)
flow = await verifier.run(flow)
```

Do not log full `Flow` or `VrakshaContext` objects:

```python
# wrong
logger.info("flow", flow=flow)

# correct
logger.info("flow", **flow.summary())
```

Do not let tools, experts, or LLMs mutate `flow` directly. They should return
structured outputs to their handler. The handler or stage updates `flow.ctx` and
returns the next `Flow`.

## Short Answer on Native Input

Do not always convert everything to plain text before the orchestrator.

Normalize into a structured object. Include text where text is the right
representation. Preserve safe native handles where native understanding matters.
The safety boundary is not "text only"; the safety boundary is sanitized input,
schema-validated normalized data, least-privileged access, and handlers that
control native artifact access.
