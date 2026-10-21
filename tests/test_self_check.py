import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(tmp, port):
    e = dict(os.environ)
    e.update({"SITE_CURATOR_PORT": str(port), "SITE_CURATOR_CACHE_DIR": str(tmp / "c"), "SITE_CURATOR_BACKUP_DIR": str(tmp / "b"),
              "SITE_CURATOR_STUDIES_DIR": str(tmp / "s"), "SITE_CURATOR_AUDIT_PATH": str(tmp / "a.jsonl")})
    e.pop("SITE_CURATOR_SITES", None)
    e.pop("METHANE_SITES_PATH", None)
    return e


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_self_check_passes_on_the_demo_roster(tmp_path):
    r = subprocess.run([sys.executable, os.path.join(HERE, "server.py"), "--check"], capture_output=True, text=True, env=_env(tmp_path, _free_port()), timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "All checks passed." in r.stdout and "FAIL" not in r.stdout


def test_self_check_reports_a_busy_port_and_a_bad_sites_file(tmp_path):
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    try:
        env = _env(tmp_path, busy.getsockname()[1])
        bad = tmp_path / "bad.json"
        bad.write_text('{"sites": [{"id": "x", "center": [200, 0], "role": "train", "box_km": 3}]}')
        env["SITE_CURATOR_SITES"] = str(bad)
        r = subprocess.run([sys.executable, os.path.join(HERE, "server.py"), "--check"], capture_output=True, text=True, env=env, timeout=120)
    finally:
        busy.close()
    assert r.returncode == 1
    assert "FAIL  port" in r.stdout and "FAIL  sites file" in r.stdout
