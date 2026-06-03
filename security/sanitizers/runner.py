import time
import asyncio

from foundation import flow, Origin, BlockReason, Threatlevel
from foundation import constants, SanitizationError
from .workers import text, pdf, image, video, audio

async def run(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw = await flow.load()
        modalities = flow.ctx.detected_modalities

        tasks = []

        if "text" in modalities: tasks.append(text.scan(raw))
        if "image" in modalities: tasks.append(image.scan(raw))
        if "pdf" in modalities: tasks.append(pdf.scan(raw))
        if "video" in modalities: tasks.append(video.scan(raw))
        if "audio" in modalities: tasks.append(audio.scan(raw))

        async with asyncio.timeout(constants.SANITIZER_TIMEOUT_TOTAL_S):
            results = await asyncio.gather(*tasks, raise_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                return flow.fail(result, Origin.SANITIZER, started)

            if result.threat_level.should_block:
                flow.ctx.sanitization_blocked = True
                flow.ctx.sanitization_blocked_reason = result.reason

                return flow.block(
                    BlockReason.MALICIOUS_CONTENT,
                    result.threat_level,
                    Origin.SANITIZER,
                    started
                )

        flow.ctx.sanitization_blocked = False
        return flow.next(results, Origin.SANITIZER, started)

    except TimeOutError:
        return flow.fail(
            SanitizationError(f"Sanitization timeout", modality="all")
            Origin.SANITIZER,
            started
        )

    except Exception as e:
        return flow.fail(e, Origin.SANITIZER, started)

