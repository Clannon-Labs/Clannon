import os
import time
import magic
from pathlib import Path

from foundation import Flow, Origin, BlockReason, ThreatLevel
from foundation import Modality, constants, PipelineStage
from foundation import (
    VrakshaError,
    InputError,
    UnsupportedModalityError,
    InputTooLargeError,
    MalformedInputError
)


def _is_too_large(file) -> bool:
    return True if Path(file).stat().st_size > constants.MAX_INPUT_SIZE_BYTES else False


def _detect_modalities(file) -> list[Modality]:
    modalities = []

    if isinstance(file, (str, os.PathLike)):
        mime = magic.from_file(file, mime=True)
        
        if mime.startswith("text/"):
            modalities.append(Modality.TEXT)
        
        elif mime.startswith("application/pdf"):
            modalities.append(Modality.PDF)

        elif mime.startswith("image/"):
            modalities.append(Modality.IMAGE)

        elif mime.startswith("audio/"):
            modalities.append(Modality.AUDIO)

        elif mime.startswith("video/"):
            modalities.append(Modality.VIDEO)

        return modalities
    
    else:
        mime = magic.from_buffer(file, mime=True)
        
        if mime.startswith("text/"):
            modalities.append(Modality.TEXT)
        
        elif mime.startswith("application/pdf"):
            modalities.append(Modality.PDF)

        elif mime.startswith("image/"):
            modalities.append(Modality.IMAGE)

        elif mime.startswith("audio/"):
            modalities.append(Modality.AUDIO)

        elif mime.startswith("video/"):
            modalities.append(Modality.VIDEO)

            

    

async def process(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw_input = await flow.load()

        if _is_too_large(raw_input):
            return flow.block(
                BlockReason.INPUT_TOO_LARGE,
                ThreatLevel.NONE,
                Origin.INTAKE,
                started
            )

        modalities = _detect_modalities(raw_input)
        if not modalities:
            return flow.block(
                BlockReason.UNSUPPORTED_MODALITY,
                ThreatLevel.NONE,
                Origin.INTAKE,
                started
            )

        flow.ctx.raw_input = raw_input
        flow.ctx.detected_modalities = [m.value for m in modalities]
        flow.ctx.advance(PipelineStage.INTAKE)

        return flow.next(raw_input, Origin.INTAKE, started)

    except Exception as e:
        return flow.fail(e, Origin.INTAKE, started)

