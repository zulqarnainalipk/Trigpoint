"""Build docs/FEATURE_GUIDE.md from help_content.json, the same file the in-tool help popups read.

    python tools/make_guide.py            # rewrites docs/FEATURE_GUIDE.md
    python tools/make_guide.py --check    # exits with 1 if the written guide is out of date

A test runs the check, so the guide and the tool can never disagree.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(path=os.path.join(HERE, "help_content.json")):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = ["# Feature guide", "",
           "Every feature of TrigPoint, in plain words. The same text opens in the tool when you press the ? button "
           "beside a control, or search it with the Guide button. This file is generated from `help_content.json`; "
           "do not edit it by hand.", "", "## Contents", ""]
    for area in data["areas"]:
        out.append(f"* [{area}](#{area.lower().replace(' ', '-')})")
    out.append("")
    for area in data["areas"]:
        out += [f"## {area}", ""]
        for key, f in data["features"].items():
            if f["area"] != area:
                continue
            out += [f"### {f['title']}", "", f"*{f['short']}*", "",
                    f"**What it is.** {f['what']}", "", f"**Why it matters.** {f['why']}", "", "**How to use it.**", ""]
            out += [f"{i}. {s}" for i, s in enumerate(f["how"], 1)]
            out += ["", f"**How it works.** {f['works']}", "", f"**What it cannot do.** {f['limits']}", ""]
            if f.get("expert"):
                out += ["**Expert details.**", ""] + [f"* {k}: `{v}`" for k, v in f["expert"].items()] + [""]
    return "\n".join(out).rstrip() + "\n"


def main(argv):
    target = os.path.join(HERE, "docs", "FEATURE_GUIDE.md")
    text = build()
    if "--check" in argv:
        try:
            with open(target, encoding="utf-8") as f:
                same = f.read() == text
        except OSError:
            same = False
        print("up to date" if same else "OUT OF DATE: run python tools/make_guide.py")
        return 0 if same else 1
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
