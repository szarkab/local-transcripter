"""Timestamp formatting and conservative repetition notices; never delete speech."""
import re


def timestamp(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"


def normalize(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def clean_reference(reference: str) -> str:
    reference = re.sub(r"^\d{2}:.*?\[Speaker \d+\]\s*", "", reference,
                       flags=re.MULTILINE)
    return re.sub(r"\[[^\]]*\]", "", reference)


def repetitions(text: str) -> list[dict[str, str | int]]:
    """Flag adjacent exact repeats; do not remove potentially real speech."""
    words = normalize(text).split()
    found: list[dict[str, str | int]] = []
    for width in range(1, 9):
        i = 0
        while i + 2 * width <= len(words):
            phrase = words[i:i + width]
            count = 1
            while words[i + count * width:i + (count + 1) * width] == phrase:
                count += 1
            if count >= 4 and count * width >= 12:
                found.append({'word_offset': i, 'phrase': ' '.join(phrase), 'count': count})
                i += count * width
            else:
                i += 1
    return found

