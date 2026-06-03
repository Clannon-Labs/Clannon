from dataclasses import dataclass
from foundation import ThreatLevel, BlockReason

@dataclass
class TextScanResult:
    threat_level: ThreatLevel
    reason: str | None = None
    passed: bool | True


async def scan(text: str) -> TextScanResult:
    """
        # --- Text Security ---
        presidio-analyzer            # PII detection
        presidio-anonymizer          # PII anonymization/redaction
        detect-secrets               # API keys, tokens, credentials detection
        bleach                       # HTML sanitization
        llm-guard                    # prompt injection, toxicity, secrets scanning
        rebuff                       # secondary prompt injection detection

    """
    pass
