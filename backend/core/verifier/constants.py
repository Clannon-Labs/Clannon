"""Small verifier constants shared across verifier modules."""

from foundation import Modality, constants


ROUTING_DIRECT = "direct"
ROUTING_EXPERT = "expert"
ROUTING_BLOCK = "block"

TEXT_MODALITIES = {Modality.TEXT.value, Modality.PDF.value}
NATIVE_MODALITIES = {
    Modality.IMAGE.value,
    Modality.AUDIO.value,
    Modality.VIDEO.value,
}
KNOWN_MODALITIES = TEXT_MODALITIES | NATIVE_MODALITIES

VERIFIER_EXCERPT_CHARS = min(8_000, constants.MAX_TEXT_INPUT_CHARS)
