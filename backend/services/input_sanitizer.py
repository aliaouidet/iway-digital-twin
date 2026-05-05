"""
Input Sanitizer — Prompt Injection Defense.

Protects the LLM pipeline from adversarial user inputs:
  1. Detects known prompt injection patterns (jailbreak, override, exfiltration)
  2. Strips dangerous control sequences (system:, ###, <|endoftext|>)
  3. Wraps user content in XML delimiters so the LLM can distinguish user vs system

Usage:
    from backend.services.input_sanitizer import sanitize_user_input
    sanitized, is_suspicious = sanitize_user_input(user_text)
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger("I-Way-Twin")


# ── Injection Patterns (regex, case-insensitive) ──────────────

_INJECTION_PATTERNS = [
    # Override/ignore instructions
    r"ignore\s+(all\s+)?(previous|prior|above|preceding)\s+(instructions?|prompts?|rules?)",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
    r"override\s+(all\s+)?(system|safety|security)\s*(instructions?|prompts?|rules?|filters?)?",
    r"you\s+are\s+now\s+(a|an|the|my)\s+",
    r"act\s+as\s+(a|an|the|if)\s+",
    r"pretend\s+(you\s+are|to\s+be)",
    r"new\s+instructions?\s*:",
    # Exfiltration attempts
    r"(show|reveal|display|print|output|return|give\s+me)\s+(all\s+)?(system|internal|hidden|secret)\s+(prompt|instructions?|data|records?|information)",
    r"(what\s+are|tell\s+me)\s+(your|the)\s+(system\s+)?(instructions?|prompts?|rules?)",
    r"repeat\s+(your|the|all)\s+(system\s+)?(instructions?|prompts?)",
    # Token manipulation
    r"<\|?(endoftext|im_start|im_end|system|assistant)\|?>",
    r"\[INST\]|\[/INST\]|\[SYS\]|\[/SYS\]",
    # Role hijacking
    r"^(system|assistant|admin)\s*:",
    r"###\s*(system|instruction|human|assistant)",
    # Data extraction
    r"(dump|export|extract|leak)\s+(all\s+)?(user|patient|client|dossier|matricule|database|db)\s*(data|records?|info)?",
]

_COMPILED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
    for pattern in _INJECTION_PATTERNS
]


# ── Dangerous Sequences to Strip ──────────────────────────────

_STRIP_SEQUENCES = [
    r"<\|endoftext\|>",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"###\s*(System|Human|Assistant|Instruction)\s*:?",
]

_COMPILED_STRIP = [
    re.compile(seq, re.IGNORECASE) for seq in _STRIP_SEQUENCES
]


def sanitize_user_input(text: str) -> Tuple[str, bool]:
    """
    Sanitize user input for safe LLM consumption.

    Returns:
        (sanitized_text, is_suspicious)
        - sanitized_text: Cleaned text wrapped in XML delimiters
        - is_suspicious: True if injection patterns were detected
    """
    if not text or not text.strip():
        return text, False

    is_suspicious = False
    matched_patterns = []

    # Step 1: Detect injection patterns
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            is_suspicious = True
            matched_patterns.append(pattern.pattern[:60])

    # Step 2: Strip dangerous control sequences
    cleaned = text
    for strip_pattern in _COMPILED_STRIP:
        cleaned = strip_pattern.sub("", cleaned)

    # Step 3: Normalize whitespace (collapse multiple spaces/newlines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    cleaned = cleaned.strip()

    # Step 4: Log suspicious inputs
    if is_suspicious:
        logger.warning(
            f"🛡️ PROMPT INJECTION DETECTED: {len(matched_patterns)} pattern(s) matched. "
            f"Input preview: {text[:100]}..."
        )

    return cleaned, is_suspicious


def wrap_user_message(text: str) -> str:
    """
    Wrap user message in XML delimiters for safe prompt injection.

    The system prompt instructs the LLM to treat content inside
    <user_message> tags as user data, never as instructions.
    """
    return f"<user_message>{text}</user_message>"
