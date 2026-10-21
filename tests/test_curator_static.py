"""Static checks that the JS and the HTML agree: every element id the scripts
look up with $("id") must exist in index.html (or be created by the scripts)."""
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")

# ids that the scripts create at run time
DYNAMIC = {"info-nb", "nb-sum", "empty-clear-filters"}


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as f:
        return f.read()


def test_every_looked_up_id_exists():
    html = read("index.html")
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    missing = {}
    for js in ("app.js", "review.js", "imagery.js", "studies.js", "help.js"):
        for m in re.finditer(r'\$\("([A-Za-z0-9_-]+)"\)', read(js)):
            if m.group(1) not in html_ids and m.group(1) not in DYNAMIC:
                missing.setdefault(js, set()).add(m.group(1))
    assert not missing, missing


def test_bar_ids_used_by_layout_code_exist():
    html = read("index.html")
    for i in ("sidebar", "panel", "btn-expand-sidebar", "btn-collapse-sidebar", "btn-expand-panel",
              "btn-collapse-panel", "sidebar-resize", "panel-resize-handle", "quick-edit", "btn-focus",
              "focus-exit", "btn-left-acc", "btn-right-acc", "rb-quick"):
        assert f'id="{i}"' in html, i


def test_no_bottom_panel_leftovers():
    css, js = read("style.css"), read("app.js") + read("review.js")
    assert "46vh" not in css and "panelHeightPx" not in js and "panelExpandedHeight" not in js
    assert "orientation=\"horizontal\"" not in read("index.html")


def test_every_accordion_key_is_unique():
    keys = re.findall(r'data-acc="([^"]+)"', read("index.html"))
    assert len(keys) == len(set(keys))


def test_no_em_dash_in_static_files():
    for name in ("index.html", "app.js", "review.js", "style.css"):
        # existing code comments may carry one; user-facing text must not
        text = read(name)
        if name == "index.html":
            assert "—" not in text
