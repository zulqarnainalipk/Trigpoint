"""Guards against markup injection through site names and other user text in the front end."""
import os
import re

STATIC = os.path.join(os.path.dirname(__file__), "..", "static")
RISKY = re.compile(r"\$\{\s*(?:[a-z]+\.(?:name|id|role|message|severity|filename|a|b|notes|comment)|name|status|id|e\.message)\s*\}")


def _templates(fn):
    src = open(os.path.join(STATIC, fn), encoding="utf-8").read()
    for m in re.finditer(r"innerHTML\s*=\s*`(.*?)`", src, re.S):
        yield m.group(1)


def test_user_text_is_escaped_in_html_templates():
    bad = []
    for fn in ("app.js", "review.js", "imagery.js", "studies.js"):
        for tpl in _templates(fn):
            bad += [m.group(0) for m in RISKY.finditer(tpl)]
    assert not bad, f"unescaped values in innerHTML templates: {bad}"