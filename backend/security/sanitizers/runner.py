"""
Sanitizer stage runner.

This is the stage-level entry point used by core/pipeline.py. It preserves the
pipeline contract: load the previous stage payload, write sanitizer findings to
flow.ctx, and return flow.next(), flow.block(), or flow.fail().

Ordering is important:

1. Universal pre-sanitization runs first on the raw payload.
2. Modality-specific workers run only if pre-sanitization passes.
3. The next payload is the sanitized worker output when available, otherwise
   the original payload from intake.
"""

import time
import asyncio
import weakref

from foundation import Flow, Origin, BlockReason, PipelineStage
from foundation import constants, SanitizationError
from . import pre_sanitization
from .workers import text, pdf, image, video, audio


# One concurrency limiter per event loop, shared across requests on that loop.
# Bounds how many modality workers run at once to constants.SANITIZER_MAX_WORKERS
# (keyed by loop so tests that spin up fresh loops don't reuse a bound semaphore).
_worker_semaphores: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


def _worker_semaphore() -> asyncio.Semaphore:
    """Return the modality-worker concurrency limiter for the running loop."""
    loop = asyncio.get_running_loop()
    semaphore = _worker_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(constants.SANITIZER_MAX_WORKERS)
        _worker_semaphores[loop] = semaphore
    return semaphore


async def _bounded_scan(scan_coro):
    """
    Run one modality worker under the global concurrency limit and a per-worker
    timeout. A worker that exceeds SANITIZER_TIMEOUT_WORKER_S raises TimeoutError,
    which the runner turns into a fail (distinct from the overall total timeout).
    """
    async with _worker_semaphore():
        async with asyncio.timeout(constants.SANITIZER_TIMEOUT_WORKER_S):
            return await scan_coro


# Maps an intake-detected modality to its sanitizer worker MODULE. The runner
# schedules a bounded scan for each detected modality present here, in this
# declaration order (preserved from the previous hardcoded dispatch). Mapping to
# the module (not the already-bound `.scan`) keeps the entry point late-bound —
# resolved at call time, exactly like the old `if "x" in modalities: x.scan(raw)`
# ladder — so a worker swapped at runtime (or in a test) is honored.
_MODALITY_WORKERS = {
    "text": text,
    "image": image,
    "pdf": pdf,
    "video": video,
    "audio": audio,
}


async def run(flow: Flow) -> Flow:
    """
    Run pre-sanitization, then all modality workers for this input.

    flow.ctx.detected_modalities is written by intake. The runner fans out to
    the matching modality workers and aggregates their scan reports. Any HIGH or
    CRITICAL threat blocks the pipeline before later stages run.
    """
    started = time.monotonic()

    try:
        raw = await flow.load()
        flow.ctx.advance(PipelineStage.SANITIZING)
        modalities = flow.ctx.detected_modalities

        # Pre-sanitization is a hard gate. No modality parser should touch the
        # input until ClamAV/YARA have had a chance to reject it.
        pre_result = await pre_sanitization.run(raw)
        if pre_result.threat_level.should_block:
            flow.ctx.sanitization = pre_result
            flow.ctx.sanitization_blocked = True
            flow.ctx.sanitization_block_reason = pre_result.reason

            return flow.block(
                BlockReason.MALICIOUS_CONTENT,
                pre_result.threat_level,
                Origin.SANITIZER,
                started
            )

        # Workers are scheduled based on intake's modality detection. Each runs
        # under the global concurrency limit + a per-worker timeout, and all run
        # concurrently under the total sanitizer timeout below.
        tasks = [
            _bounded_scan(worker.scan(raw))
            for modality, worker in _MODALITY_WORKERS.items()
            if modality in modalities
        ]
        if not tasks:
            return flow.block(
                BlockReason.UNSUPPORTED_MODALITY,
                pre_result.threat_level,
                Origin.SANITIZER,
                started
            )

        async with asyncio.timeout(constants.SANITIZER_TIMEOUT_TOTAL_S):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # The default handoff is the original payload. Workers can replace it
        # with sanitized_text/sanitized_image-style outputs when they produce a
        # safe payload for downstream stages.
        sanitized_payload = raw
        sanitized_outputs = {}
        for result in results:
            if isinstance(result, Exception):
                return flow.fail(result, Origin.SANITIZER, started)

            for kind in ("text", "image", "pdf", "audio", "video"):
                sanitized = getattr(result, f"sanitized_{kind}", None)
                if sanitized is not None:
                    sanitized_payload = sanitized
                    sanitized_outputs[kind] = sanitized

            if result.threat_level.should_block:
                # Persist the report on the same block path as pre-sanitization
                # so dead-letter inspection keeps the worker findings.
                flow.ctx.sanitization = {
                    "pre_sanitization": pre_result,
                    "workers": results,
                    "sanitized_outputs": sanitized_outputs,
                }
                flow.ctx.sanitization_blocked = True
                flow.ctx.sanitization_block_reason = result.reason

                return flow.block(
                    BlockReason.MALICIOUS_CONTENT,
                    result.threat_level,
                    Origin.SANITIZER,
                    started
                )

        flow.ctx.sanitization_blocked = False
        flow.ctx.sanitization = {
            "pre_sanitization": pre_result,
            "workers": results,
            "sanitized_outputs": sanitized_outputs,
        }
        return flow.next(sanitized_payload, Origin.SANITIZER, started)

    except TimeoutError:
        return flow.fail(
            SanitizationError(f"Sanitization timeout", modality="all"),
            Origin.SANITIZER,
            started
        )

    except Exception as e:
        return flow.fail(e, Origin.SANITIZER, started)
