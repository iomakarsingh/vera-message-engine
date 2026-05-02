"""
Category-specific voice rules and validation.
Extracted from the 5 category JSON files in the dataset.
"""

from __future__ import annotations

from typing import Optional


# ── Voice instruction generators ─────────────────────────────────────────────

def get_voice_instructions(category: dict) -> str:
    """Build LLM prompt fragment describing the category voice rules."""
    slug = category.get("slug", "unknown")
    voice = category.get("voice", {})
    tone = voice.get("tone", "professional")
    taboos = voice.get("vocab_taboo", [])
    allowed = voice.get("vocab_allowed", [])
    salutations = voice.get("salutation_examples", [])
    tone_examples = voice.get("tone_examples", [])

    lines = [
        f"## VOICE RULES — {slug.upper()} category",
        f"Tone: {tone}",
        f"Register: {voice.get('register', 'professional')}",
        f"Language mixing: {voice.get('code_mix', 'natural')}",
    ]

    if allowed:
        lines.append(f"Vocabulary encouraged: {', '.join(allowed[:10])}")

    if taboos:
        lines.append(f"NEVER use these words/phrases: {', '.join(taboos)}")

    if salutations:
        lines.append(f"Salutation style: {', '.join(salutations)}")

    if tone_examples:
        lines.append("Tone examples (match this register):")
        for ex in tone_examples:
            lines.append(f"  - \"{ex}\"")

    # Category-specific voice guidance
    voice_guides = {
        "dentists": (
            "Sound like a well-read peer dentist, not a marketer. "
            "Technical clinical terms are welcome and expected. "
            "Always cite sources when referencing research. "
            "Use 'Dr.' prefix when addressing the merchant. "
            "No overclaiming — no 'guaranteed', 'cure', '100% safe'."
        ),
        "salons": (
            "Sound like a friendly fellow salon operator who knows the business. "
            "Warm, practical, action-oriented. Use brand names when relevant. "
            "Emojis sparingly (💇 💍 ✨). "
            "No hype — no 'guaranteed glow', 'permanent results'."
        ),
        "restaurants": (
            "Sound like a fellow restaurant operator who gets the grind. "
            "Use industry terms: 'covers', 'AOV', 'dine-in vs delivery split'. "
            "Time-sensitive, practical, no-nonsense. "
            "No 'best food in city' or 'guaranteed packed house'."
        ),
        "gyms": (
            "Sound like a coach/business partner — energetic but disciplined. "
            "Use fitness vocabulary naturally: 'HIIT', 'retention', 'trial-to-paid'. "
            "Motivational but realistic — no 'guaranteed weight loss' or 'shred in 7 days'. "
            "Data-driven recommendations about membership and engagement."
        ),
        "pharmacies": (
            "Sound trustworthy and precise — like a senior pharmacist peer. "
            "Use molecule names, batch numbers, dosage details when relevant. "
            "Respectful of senior citizens — use 'Namaste', 'ji' suffix. "
            "No 'miracle cure', 'guaranteed result', '100% safe'. "
            "When addressing through son/daughter channel, be respectful of the arrangement."
        ),
    }

    guide = voice_guides.get(slug, "Professional and helpful tone.")
    lines.append(f"\nVoice guidance: {guide}")

    return "\n".join(lines)


def get_salutation(merchant: dict, category: dict) -> str:
    """Get the appropriate salutation for a merchant based on category voice."""
    slug = category.get("slug", "")
    identity = merchant.get("identity", {})
    owner_name = identity.get("owner_first_name", "")
    biz_name = identity.get("name", "")

    if slug == "dentists" and owner_name:
        return f"Dr. {owner_name}"
    elif owner_name:
        return owner_name
    elif biz_name:
        return biz_name
    return "there"


def get_customer_salutation(customer: dict) -> str:
    """Get appropriate salutation for a customer."""
    identity = customer.get("identity", {})
    name = identity.get("name", "")

    # Handle senior citizens
    if identity.get("senior_citizen"):
        return f"{name} ji" if name else "ji"

    return name if name else "there"


def validate_taboos(body: str, category: dict) -> list[str]:
    """Check message body for taboo vocabulary. Returns list of violations."""
    voice = category.get("voice", {})
    taboos = voice.get("vocab_taboo", [])
    body_lower = body.lower()

    violations = []
    for taboo in taboos:
        # Handle parenthetical notes like "FDA-approved (use only when actually applicable)"
        clean_taboo = taboo.split("(")[0].strip().lower()
        if clean_taboo and clean_taboo in body_lower:
            violations.append(taboo)

    return violations


def get_language_instruction(merchant: dict, customer: Optional[dict] = None) -> str:
    """Get language preference instruction for the LLM prompt."""
    # Customer language takes priority for customer-facing messages
    if customer:
        lang = customer.get("identity", {}).get("language_pref", "")
        if lang:
            return _lang_instruction(lang)

    # Fall back to merchant languages
    languages = merchant.get("identity", {}).get("languages", ["en"])
    if "hi" in languages and "en" in languages:
        return _lang_instruction("hi-en mix")
    elif "hi" in languages:
        return _lang_instruction("hi")
    elif "ta" in languages and "en" in languages:
        return _lang_instruction("ta-en mix")
    elif "te" in languages and "en" in languages:
        return _lang_instruction("te-en mix")
    elif "kn" in languages and "en" in languages:
        return _lang_instruction("kn-en mix")
    elif "mr" in languages and "en" in languages:
        return _lang_instruction("mr-en mix")
    return _lang_instruction("english")


def _lang_instruction(lang_pref: str) -> str:
    """Convert a language preference string to an LLM instruction."""
    mapping = {
        "hi-en mix": "Write in natural Hindi-English code-mix (Hinglish). Mix Hindi and English naturally as Indian professionals do.",
        "hi": "Write primarily in Hindi (Devanagari script not required — romanized Hindi is fine). Mix in English terms when natural.",
        "english": "Write in clear, concise English.",
        "en": "Write in clear, concise English.",
        "ta-en mix": "Write primarily in English with occasional Tamil terms where natural.",
        "te-en mix": "Write primarily in English with occasional Telugu terms where natural.",
        "kn-en mix": "Write primarily in English with occasional Kannada terms where natural.",
        "mr-en mix": "Write primarily in English with occasional Marathi terms where natural.",
    }
    return mapping.get(lang_pref.lower(), "Write in clear, concise English.")
