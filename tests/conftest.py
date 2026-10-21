"""Shared fixtures for the TrigPoint tests.

server.py reads its paths from environment variables when it is imported, so
they are set here, before the first import, to a temporary folder. The tests
never touch the real sites files, backups, cache or audit log.
"""
import json
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CURATOR = os.path.dirname(HERE)
sys.path.insert(0, CURATOR)

_TMP = tempfile.mkdtemp(prefix="curator_tests_")
SITES_FILE = os.path.join(_TMP, "sites_under_test.json")
REF_FILE = os.path.join(_TMP, "pilot_under_test.json")
os.environ["METHANE_SITES_PATH"] = SITES_FILE
os.environ["METHANE_REFERENCE_PATH"] = REF_FILE
os.environ["SITE_CURATOR_BACKUP_DIR"] = os.path.join(_TMP, "backups")
os.environ["SITE_CURATOR_CACHE_DIR"] = os.path.join(_TMP, "cache")
os.environ["SITE_CURATOR_AUDIT_PATH"] = os.path.join(_TMP, "audit.jsonl")
os.environ["SITE_CURATOR_STUDIES_DIR"] = os.path.join(_TMP, "studies")

NOTE_SCREENED = ("Setting: coastal. Coordinates: medium confidence, check the centre and box. "
                 "Screening (2025): land 25% of the 10 km window, 12 of 80 Sentinel-2 scenes clear, "
                 "NO2 contrast 5.2 umol/m2, CO contrast n/a mmol/m2, fire detection days 3. "
                 "Priority C; window is mostly water (gas values would be blank); "
                 "few clear Sentinel-2 scenes (cloudy). "
                 "Within 150 km of other candidates: b_site.")


def make_sites():
    def site(i, name, lat, lon, **kw):
        s = {"id": i, "name": name, "role": "train", "center": [lat, lon], "box_km": 3.0,
             "notes": "", "verified": False, "region": "test_region",
             "facility_type": "refinery", "coord_confidence": "medium", "priority": None}
        s.update(kw)
        return s
    return {
        "_README": ["test file"],
        "sites": [
            site("a_site", "A site", 10.0, 10.0, notes=NOTE_SCREENED, priority="C"),
            site("b_site", "B site", 10.5, 10.0),                        # about 55 km from a_site
            site("c_far", "C far", 40.0, 40.0, coord_confidence="high"),
            site("d_near_pilot", "D near pilot", -20.0, 100.0),          # near pilot_test
            site("e_between", "E between pilots", 0.0, 0.0),             # near both pilot roles
            site("f_dup", "F duplicate of A", 10.005, 10.0),             # under 1 km from a_site
        ],
        "extra_top_level": {"keep": True},
    }


def make_ref():
    return {"sites": [
        {"id": "pilot_test", "name": "Pilot test", "role": "test", "center": [-20.5, 100.0],
         "box_km": 4.0, "verified": True, "notes": ""},
        {"id": "pilot_train", "name": "Pilot train", "role": "train", "center": [0.0, 1.0],
         "box_km": 4.0, "verified": True, "notes": ""},
        {"id": "pilot_test2", "name": "Pilot test 2", "role": "test", "center": [0.0, -1.0],
         "box_km": 4.0, "verified": True, "notes": ""},
    ]}


def write_files():
    with open(SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(make_sites(), f)
    with open(REF_FILE, "w", encoding="utf-8") as f:
        json.dump(make_ref(), f)


@pytest.fixture()
def srv():
    """The imported server module with fresh files and empty undo stacks."""
    import server
    write_files()
    import shutil
    shutil.rmtree(server.STUDIES_DIR, ignore_errors=True)
    os.makedirs(server.STUDIES_DIR, exist_ok=True)
    server.STUDIES.last.clear()
    server.UNDO_STACK.clear()
    server.REDO_STACK.clear()
    return server


@pytest.fixture()
def http(srv):
    """A real HTTP server on a free port; returns a small request helper."""
    import urllib.request
    import urllib.error

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(method, path, body=None, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Site-Curator": "test"})
        try:
            with urllib.request.urlopen(req) as r:
                payload = r.read()
                return r.status, (payload if raw else json.loads(payload)), dict(r.headers)
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                return e.code, json.loads(payload), dict(e.headers)
            except ValueError:
                return e.code, payload, dict(e.headers)

    yield call
    httpd.shutdown()
    httpd.server_close()
