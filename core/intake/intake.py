import os
import time
import magic
from pathlib import Path

from foundation import Flow, Origin, BlockReason, ThreatLevel
from foundation import Modality, constants, PipelineStage
from foundation import (
    UnsupportedModalityError,
    InputTooLargeError,
    MalformedInputError
)
from .rate_limiter import check_request_rate


def _is_too_large(file) -> bool:
    try:
        if isinstance(file, os.PathLike):
            return Path(file).stat().st_size > constants.MAX_INPUT_SIZE_BYTES

        elif isinstance(file, str):
            possible_path = Path(file)
            try:
                is_file_path = "\n" not in file and possible_path.exists() and possible_path.is_file()
            except OSError:
                is_file_path = False

            if is_file_path:
                return possible_path.stat().st_size > constants.MAX_INPUT_SIZE_BYTES
            return len(file.encode("utf-8", errors="replace")) > constants.MAX_INPUT_SIZE_BYTES

        elif isinstance(file, (bytes, bytearray, memoryview)):
            return len(file) > constants.MAX_INPUT_SIZE_BYTES

        else:
            raise InputTooLargeError("cannot determine size of input type")

    except (OSError, PermissionError) as e:
        raise MalformedInputError("could not read input file", cause=e)


def _detect_modalities(file) -> list[Modality]:
    modalities = []

    try:
        if isinstance(file, os.PathLike):
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

            else:
                raise UnsupportedModalityError(f"Unsupported modality {mime}")

            return modalities

        elif isinstance(file, str):
            possible_path = Path(file)
            try:
                is_file_path = "\n" not in file and possible_path.exists() and possible_path.is_file()
            except OSError:
                is_file_path = False

            if is_file_path:
                mime = magic.from_file(str(possible_path), mime=True)
            else:
                mime = magic.from_buffer(file.encode("utf-8", errors="replace"), mime=True)

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

            else:
                raise UnsupportedModalityError(f"Unsupported modality {mime}")

            return modalities

        else:
            if isinstance(file, bytearray):
                file = bytes(file)
            elif isinstance(file, memoryview):
                file = file.tobytes()

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

            else:
                raise UnsupportedModalityError(f"Unsupported modality {mime}")

            return modalities

    except UnsupportedModalityError:
        raise

    except Exception as e:
        raise MalformedInputError("Could not detect mime type", cause=e)

async def process(flow: Flow) -> Flow:
    started = time.monotonic()

    try:
        raw_input = await flow.load() # Load the payload/data in its current condition

        rate_limit = check_request_rate(flow.ctx.session_id)
        if not rate_limit.allowed:
            return flow.block(
                BlockReason.RATE_LIMITED,
                ThreatLevel.NONE,
                Origin.INTAKE,
                started
            )

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

        # Forward it to next layer in the pipeline
        # This creates a new flow object but with the same old context
        return flow.next(raw_input, Origin.INTAKE, started)

    except UnsupportedModalityError as e:
        return flow.block(
            BlockReason.UNSUPPORTED_MODALITY,
            ThreatLevel.HIGH,
            Origin.INTAKE,
            started
        )

    except MalformedInputError as e:
        # expected bad input.. block, not fail
        return flow.block(
            BlockReason.MALFORMED_INPUT,
            ThreatLevel.NONE,
            Origin.INTAKE,
            started
        )

    except Exception as e:
        return flow.fail(e, Origin.INTAKE, started)
