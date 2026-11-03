import string

_PUNCTUATION_TO_SPACE = str.maketrans({char: " " for char in string.punctuation})


def normalize_text(value: str) -> str:
    """Normalize free text for matching: case-fold, drop ASCII punctuation, collapse spaces.

    Non-ASCII characters (e.g. Devanagari letters and matras) are kept intact.
    """
    return " ".join(value.casefold().translate(_PUNCTUATION_TO_SPACE).split())
