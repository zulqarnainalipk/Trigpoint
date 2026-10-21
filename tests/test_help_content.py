"""The help text: complete, readable, linked to real controls, and identical in the tool and the written guide."""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(HERE, "static")


def read(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
        return f.read()


HELP = json.loads(read("help_content.json"))
FEATURES = HELP["features"]
REQUIRED = ("area", "title", "short", "what", "why", "how", "works", "limits")


@pytest.mark.parametrize("key", sorted(FEATURES))
def test_each_entry_is_complete(key):
    f = FEATURES[key]
    for field in REQUIRED:
        assert f.get(field), f"{key}: {field} is empty"
    assert f["area"] in HELP["areas"], key
    assert isinstance(f["how"], list) and all(isinstance(s, str) and s.strip() for s in f["how"]), key
    assert 3 <= len(f["title"]) <= 60, key


def texts(f):
    out = [f["short"], f["what"], f["why"], f["works"], f["limits"], *f["how"]]
    return [t for t in out if isinstance(t, str)]


def test_no_placeholders_dashes_or_odd_characters():
    for key, f in FEATURES.items():
        for t in texts(f) + [f["title"]]:
            assert not re.search(r"TODO|TBD|lorem|FIXME", t, re.I), (key, t)
            assert "—" not in t and "–" not in t, (key, "dash")
            assert "â" not in t and "Ã" not in t, (key, "garbled character")


def test_sentences_are_short_enough_to_read_easily():
    """Plain language: no sentence over 38 words, and the average under 22 per entry."""
    for key, f in FEATURES.items():
        sentences = [s for t in texts(f) for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
        longest = max(len(s.split()) for s in sentences)
        assert longest <= 38, (key, longest, max(sentences, key=lambda s: len(s.split())))
        assert sum(len(s.split()) for s in sentences) / len(sentences) <= 22, key


def test_every_entry_says_what_it_cannot_do_in_a_full_sentence():
    for key, f in FEATURES.items():
        assert f["limits"].rstrip().endswith((".", "?")), key
        assert len(f["limits"].split()) >= 4, key


def referenced_keys():
    """Help keys used by the page: data-help in the HTML and in the scripts, and the accordion map."""
    keys = set()
    for name in ("index.html", "app.js", "review.js", "imagery.js", "studies.js", "help.js"):
        text = read("static", name)
        keys |= set(re.findall(r'data-help="([A-Za-z0-9_:]+)"', text))
        keys |= set(re.findall(r'helpBtnHtml\("([A-Za-z0-9_:]+)"', text))
    keys |= set(re.findall(r'"r-[a-z-]+": "([a-z_]+)"', read("static", "review.js")))      # ACC_HELP
    return keys


def test_every_help_button_has_an_entry():
    unknown = {k for k in referenced_keys() if k not in FEATURES and not k.startswith(("index:", "composite:"))}
    assert not unknown, unknown


def test_every_entry_is_reachable_from_a_button():
    unreached = set(FEATURES) - referenced_keys()
    assert not unreached, f"no ? button opens these entries: {sorted(unreached)}"


def test_dynamic_entries_exist_for_every_index_and_view(http):
    code, v, _ = http("GET", "/api/views")
    assert code == 200
    for name, i in v["indices"].items():
        assert i["formula"] and i["description"].strip().endswith("."), name
    for name, c in v["composites"].items():
        assert c["description"].strip() and c["bands"], name


def test_nothing_else_uses_the_data_help_attribute():
    """data-help marks help buttons only. A page-level attribute of that name once made every click open help."""
    html = read("static", "index.html")
    for m in re.finditer(r'<([a-z0-9]+)\s[^>]*data-help="', html):
        assert m.group(1) == "button", m.group(0)[:60]
    for name in ("app.js", "review.js", "imagery.js", "studies.js"):
        assert "documentElement.dataset.help =" not in read("static", name), name
    css = read("static", "style.css")
    assert ':root[data-help=' not in css


def test_help_buttons_have_a_name_and_open_a_dialog():
    for m in re.finditer(r'<button[^>]*data-help="[^"]+"[^>]*>', read("static", "index.html")):
        tag = m.group(0)
        assert 'aria-label="' in tag and 'aria-haspopup="dialog"' in tag, tag[:80]
        assert 'type="button"' in tag, tag[:80]


def test_the_written_guide_is_up_to_date():
    r = subprocess.run([sys.executable, os.path.join(HERE, "tools", "make_guide.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
