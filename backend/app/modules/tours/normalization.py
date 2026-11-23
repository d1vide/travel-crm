import unicodedata


def normalize_destination(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold()


def contains_destination(value: str) -> str:
    value = normalize_destination(value)
    value = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{value}%"
