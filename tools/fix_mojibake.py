"""Repair text that was saved after being decoded with the wrong character set (for example "â€”" for an em dash).

    python tools/fix_mojibake.py FILE [FILE ...]        # rewrites the files in place and prints what it changed

A run of characters that looks like UTF-8 bytes read as Windows-1252 is converted back. Runs that are already
correct text are left alone, so the tool is safe to run twice.
"""
import re
import sys

# characters that appear when UTF-8 bytes are shown as Windows-1252
_MOJI = re.compile(r"[Â-ô][\u0080-¿ŒœŠšŸŽžƒˆ˜"
                   r"–—‘’‚“”„†‡•…‰‹›€™]"
                   r"(?:[Â-ô]?[\u0080-¿ŒœŠšŸŽžƒˆ˜"
                   r"–—‘’‚“”„†‡•…‰‹›€™])*")


def _undo(run):
    try:
        return run.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    try:
        return run.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return run


def fix_text(text):
    """Return (fixed text, number of runs repaired). Handles text that was mangled twice."""
    total = 0
    for _ in range(3):
        count = 0

        def sub(m):
            nonlocal count
            fixed = _undo(m.group(0))
            if fixed != m.group(0):
                count += 1
            return fixed

        text = _MOJI.sub(sub, text)
        total += count
        if not count:
            break
    return text, total


def main(paths):
    for p in paths:
        with open(p, "r", encoding="utf-8", newline="") as f:
            text = f.read()
        fixed, n = fix_text(text)
        if n:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(fixed)
        print(f"{p}: {n} repaired")


if __name__ == "__main__":
    main(sys.argv[1:])
