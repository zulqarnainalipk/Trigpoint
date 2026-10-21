"""The licence and citation files exist and agree with each other and with the README."""
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(n):
    with open(os.path.join(HERE, n), encoding="utf-8") as f:
        return f.read()


def test_licence_and_citation_agree():
    lic, cff, readme = read("LICENSE"), read("CITATION.cff"), read("README.md")
    assert "Attribution-NonCommercial 4.0" in lic and "legalcode" in lic and "Zulqarnain Ali" in lic
    assert "license: CC-BY-NC-4.0" in cff and "Zulqarnain" in cff and "0009-0009-0281-882X" in cff
    assert "CC BY-NC 4.0" in readme and "CITATION.cff" in readme
    version = re.search(r'VERSION = "([^"]+)"', read("server.py")).group(1)
    assert f'version: "{version}"' in cff
