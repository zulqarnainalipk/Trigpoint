"""The visible name is TrigPoint everywhere a person reads it; internal names are the ones listed in the README."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# names that were deliberately kept (see "Names you will still see" in the README)
KEPT = ("SITE_CURATOR_", "X-Site-Curator", "site-curator-", "site_curator", "curator_logic")


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as f:
        return f.read()


def test_no_document_or_page_still_says_site_curator_as_a_name():
    skip_dirs = {"__pycache__", ".pytest_cache", "cache", "backups", "studies", "tests"}
    offenders = []
    for d, dirs, files in os.walk(HERE):
        dirs[:] = [x for x in dirs if x not in skip_dirs]
        for f in files:
            if not f.endswith((".py", ".js", ".html", ".css", ".json", ".md", ".yml", ".cff", ".bat", ".sh", ".svg")) and f not in ("Dockerfile", "LICENSE"):
                continue
            text = read(os.path.relpath(os.path.join(d, f), HERE))
            for m in re.finditer(r"Site[ -]Curator", text):
                line = text[max(0, text.rfind("\n", 0, m.start()) + 1):text.find("\n", m.end())]
                if "formerly Site Curator" in line or "first called Site Curator" in line or "Renamed from Site Curator" in line or "X-Site-Curator" in line:
                    continue
                offenders.append((f, line.strip()[:80]))
    assert not offenders, offenders


def test_the_page_uses_the_new_name_and_logo():
    html = read("static", "index.html")
    assert "<title>TrigPoint</title>" in html and "<span>TrigPoint</span>" in html
    assert 'href="/logo.svg"' in html and "brand-logo" in html
    assert "polygon(50% 0, 100% 50%, 50% 100%, 0 50%)" not in read("static", "style.css")                    # the old diamond is gone


def test_the_logo_file_is_a_valid_nested_squares_image():
    svg = read("static", "logo.svg")
    assert svg.startswith("<svg") and "<title>TrigPoint</title>" in svg and svg.count("<rect") == 3 and "stroke-dasharray" in svg
    import xml.dom.minidom as md
    md.parseString(svg)


def test_the_logo_is_served(http):
    code, body, hdr = http("GET", "/logo.svg", raw=True)
    assert code == 200 and hdr["Content-Type"].startswith("image/svg+xml") and b"TrigPoint" in body


def test_provenance_and_citation_use_the_new_name():
    assert '"name": "TrigPoint"' in read("provenance.py") and 'title: "TrigPoint"' in read("CITATION.cff")
    assert read("LICENSE").startswith("TrigPoint")
