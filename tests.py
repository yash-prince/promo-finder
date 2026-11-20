"""Quick checks for the code-owned parts (no API key needed):  python tests.py <episode folder>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parser import load_folder
from validate import validate

eps = load_folder(sys.argv[1], 3)
assert len(eps) == 3 and all(e.beats for e in eps), "parser found no beats"
e = eps[0]


def check(name, segs, expect_ok):
    cand, why = validate({"segments": segs}, e, "T")
    ok = cand is not None
    assert ok == expect_ok, f"{name}: expected ok={expect_ok}, got {why or cand.duration}"
    if ok:
        assert 20 <= cand.duration <= 60, f"{name}: length {cand.duration} outside 20-60"
    print("pass:", name, "->", "accepted" if ok else f"rejected ({why})")


check("valid clip", [{"start": "00:11.3", "end": "00:45.0"}], True)
check("invented timestamp", [{"start": "00:05.0", "end": "00:55.0"}], False)
check("too long is trimmed to <=60s", [{"start": "00:01.0", "end": "02:10.0"}], True)
check("too short is rejected", [{"start": "00:11.3", "end": "00:19.4"}], False)
check("end before start", [{"start": "00:40.0", "end": "00:30.0"}], False)
print("all good")
