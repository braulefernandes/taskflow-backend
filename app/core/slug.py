import re
import unicodedata

SLUG_MAX_LENGTH = 120


def slugify(value: str, *, max_length: int = SLUG_MAX_LENGTH) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_length].strip("-") or "organization"


def slug_with_suffix(base_slug: str, suffix: int, *, max_length: int = SLUG_MAX_LENGTH) -> str:
    suffix_text = f"-{suffix}"
    return f"{base_slug[: max_length - len(suffix_text)].strip('-')}{suffix_text}"
