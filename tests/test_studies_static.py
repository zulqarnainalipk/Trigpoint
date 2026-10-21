"""The studies page: every element the script looks for exists, and the dialog is built for keyboard and screen reader use."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*p):
    with open(os.path.join(HERE, *p), encoding="utf-8") as f:
        return f.read()


HTML = read("static", "index.html")
JS = read("static", "studies.js")
IDS = set(re.findall(r'\bid="([^"]+)"', HTML))


def test_every_element_the_script_uses_exists_in_the_page():
    used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', JS))
    assert used, "the script uses no elements?"
    missing = sorted(u for u in used if u not in IDS)
    assert not missing, missing


def test_the_script_is_loaded_before_app_js_and_served():
    assert HTML.index("/studies.js") < HTML.index("/app.js")
    assert '"/studies.js"' in read("server.py")


def test_tabs_follow_the_tab_pattern():
    dlg = HTML[HTML.index('id="studies-dialog"'):]
    dlg = dlg[:dlg.index("</dialog>")]
    tabs = re.findall(r'<button[^>]*role="tab"[^>]*>', dlg)
    panels = re.findall(r'<section[^>]*role="tabpanel"[^>]*>', dlg)
    assert len(tabs) == len(panels) == 4
    for t in tabs:
        controls = re.search(r'aria-controls="([^"]+)"', t).group(1)
        assert f'id="{controls}"' in dlg and "aria-selected" in t
    assert 'role="tablist"' in dlg
    for p in panels:
        assert "aria-labelledby" in p


def test_every_control_in_the_dialog_has_a_visible_label_or_a_name():
    dlg = HTML[HTML.index('id="studies-dialog"'):]
    dlg = dlg[:dlg.index("</dialog>")]
    for m in re.finditer(r'<(input|select|textarea)\b([^>]*)>', dlg):
        attrs = m.group(2)
        iid = re.search(r'\bid="([^"]+)"', attrs)
        if re.search(r'type="(checkbox|radio)"', attrs):
            continue                                              # these sit inside their label
        assert iid, attrs
        assert f'for="{iid.group(1)}"' in dlg or "aria-label" in attrs, iid.group(1)


def test_results_are_never_inserted_as_markup():
    assert "innerHTML" not in JS and "insertAdjacentHTML" not in JS and "outerHTML" not in JS


def test_results_regions_are_announced():
    for rid in ("st-groups-out", "st-dup-out", "st-shift-out", "st-cert-out", "st-fc-out", "st-gr-out", "st-pl-out"):
        assert re.search(rf'id="{rid}"[^>]*aria-live="polite"', HTML), rid


def test_charts_have_text_alternatives():
    assert JS.count('"role", "img"') >= 2 and JS.count("aria-label") >= 2
