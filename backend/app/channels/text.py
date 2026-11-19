"""Plain-text formatting for handsets: ASCII only (GSM-7 safe) and split into pages."""

import unicodedata

USSD_MAX_CHARS = 182
SMS_MAX_CHARS = 160


def ascii_text(value: str) -> str:
    """Transliterate to ASCII so every handset and SMS gateway can display it."""
    replaced = (
        value.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u20a6", "NGN ")
    )
    return unicodedata.normalize("NFKD", replaced).encode("ascii", "ignore").decode("ascii")


def number(value: int) -> str:
    return f"{value:,}"


def percent(part: int, whole: int) -> str:
    if whole <= 0:
        return "n/a"
    return f"{100 * part / whole:.1f}%".replace(".0%", "%")


def truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: max(0, limit - 3)].rstrip() + "..."


def _wrap(line: str, limit: int) -> list[str]:
    words, out, current = line.split(" "), [], ""
    for word in words:
        while len(word) > limit:
            if current:
                out.append(current)
                current = ""
            out.append(word[:limit])
            word = word[limit:]
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out


def paginate(lines: list[str], limit: int) -> list[str]:
    """Pack whole lines into pages of at most `limit` characters."""
    pages: list[str] = []
    current = ""
    for raw in lines:
        for line in _wrap(ascii_text(raw), limit):
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= limit:
                current = candidate
            else:
                pages.append(current)
                current = line
    if current:
        pages.append(current)
    return pages or [""]


def sms_parts(lines: list[str], limit: int = SMS_MAX_CHARS) -> list[str]:
    """Split into SMS-sized parts, each numbered "(n/m)" when there is more than one."""
    pages = paginate([" ".join(line.split()) for line in lines], limit)
    if len(pages) == 1:
        return pages
    # Reserve room for the "(nn/nn) " prefix and repaginate.
    pages = paginate([" ".join(line.split()) for line in lines], limit - 8)
    return [f"({i}/{len(pages)}) {page}" for i, page in enumerate(pages, start=1)]
