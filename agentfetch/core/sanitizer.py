import re
import logging

logger = logging.getLogger("agentfetch.sanitizer")

PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?(?:above\s+)?(?:instructions|prompts|rules)",
    r"you are now",
    r"new persona",
    r"system prompt",
    r"forget\s+(everything|what)",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"###\s*instruction",
    r"disregard\s+(your|all|previous)",
    r"act as\s+(a\s+|an\s+)?(different|new|unrestricted)",
    r"do not follow",
    r"jailbreak",
    r"DAN mode",
]

REDACTED = "[REDACTED BY AGENTFETCH]"


def sanitize(text: str, url: str = "") -> tuple[str, bool]:
    injection_detected = False
    result = text

    for pattern in PATTERNS:
        if re.search(pattern, result, re.IGNORECASE):
            injection_detected = True
            logger.warning("Injection detected | url=%s | pattern=%s", url, pattern)
            result = re.sub(pattern, REDACTED, result, flags=re.IGNORECASE)

    return result, injection_detected
