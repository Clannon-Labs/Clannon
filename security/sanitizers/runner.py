import time
import asyncio

from foundation import Flow, Origin, BlockReason
from foundation import constants, SanitizationError
from . import pre_sanitization
from .workers import text, pdf, image, video, audio


async def run(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw = await flow.load()
        modalities = flow.ctx.detected_modalities

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

        tasks = []

        if "text" in modalities: tasks.append(text.scan(raw))
        if "image" in modalities: tasks.append(image.scan(raw))
        if "pdf" in modalities: tasks.append(pdf.scan(raw))
        if "video" in modalities: tasks.append(video.scan(raw))
        if "audio" in modalities: tasks.append(audio.scan(raw))

        async with asyncio.timeout(constants.SANITIZER_TIMEOUT_TOTAL_S):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        sanitized_payload = raw
        for result in results:
            if isinstance(result, Exception):
                return flow.fail(result, Origin.SANITIZER, started)

            result_sanitized_text = getattr(result, "sanitized_text", None)
            if result_sanitized_text is not None:
                sanitized_payload = result_sanitized_text

            if result.threat_level.should_block:
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
