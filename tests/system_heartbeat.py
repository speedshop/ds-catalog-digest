import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory(dir="/tmp") as directory:
    work = Path(directory)
    fake = work / "gh"
    fake.write_text(f"#!{sys.executable}\nimport json, os\nfrom pathlib import Path\np=Path(os.environ['HEARTBEAT_TEST_COUNTER'])\nn=int(p.read_text()) if p.exists() else 0\np.write_text(str(n+1))\nids=json.loads(os.environ['HEARTBEAT_TEST_LISTING'])\nprint(json.dumps([{{'databaseId': ids[min(n,len(ids)-1)]}}]))\n")
    fake.chmod(0o755)
    event = work / "event.json"
    driver = work / "driver.py"
    driver.write_text('import os, runpy, sys, time, urllib.request\nfrom pathlib import Path\nsys.path.insert(0,str(Path(sys.argv[1]).parent))\nclass Response:\n status=int(os.environ["HEARTBEAT_TEST_STATUS"])\n def __enter__(self): return self\n def __exit__(self,*args): pass\ndef request(*args,**kwargs):\n print("CHECK_IN")\n return Response()\nurllib.request.urlopen=request\ntime.sleep=lambda _:None\nrunpy.run_path(sys.argv[1],run_name="__main__")\n')
    url = "https://nosnch.in/system-test-fixture"
    environment = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"], GITHUB_REPOSITORY="example/catalog", GITHUB_EVENT_PATH=str(event), DMS_CHECK_IN_URL=url)
    for run_id, conclusion, secret, status, listing, success, checked_in in (
        (9, "success", url, 200, [9], True, True),
        (9, "success", url, 202, [9], True, True),
        (9, "success", url, 204, [9], True, True),
        (9, "success", url, 304, [9], False, True),
        (8, "success", url, 200, [9], True, False),
        (9, "success", url, 202, [8, 9], True, True),
        (9, "success", url, 202, [8], False, False),
        (9, "success", url, 202, [10], True, False),
        (9, "failure", url, 200, [9], True, False),
        (9, "success", "", 200, [9], False, False),
        (9, "success", "http://nosnch.in/system-test-fixture", 200, [9], False, False),
        (9, "success", "https://example.com/system-test-fixture", 200, [9], False, False),
    ):
        counter = work / "counter"
        counter.write_text("0")
        event.write_text(json.dumps({"workflow_run": {"id": run_id, "conclusion": conclusion}}))
        result = subprocess.run([sys.executable, str(driver), str(ROOT / "scripts/heartbeat.py")], env=environment | {"DMS_CHECK_IN_URL": secret, "HEARTBEAT_TEST_STATUS": str(status), "HEARTBEAT_TEST_LISTING": json.dumps(listing), "HEARTBEAT_TEST_COUNTER": str(counter)}, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stderr
        assert ("CHECK_IN" in result.stdout) == checked_in
        assert url not in result.stdout + result.stderr
        assert int(counter.read_text()) <= 12

print("System heartbeat: latest successful refresh only, stale/failing runs ignored, secret URL validation, no URL logging passed")
