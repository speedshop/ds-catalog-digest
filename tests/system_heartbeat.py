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
    fake.write_text(f"#!{sys.executable}\nimport json\nprint(json.dumps([{{'databaseId': 9}}]))\n")
    fake.chmod(0o755)
    event = work / "event.json"
    driver = work / "driver.py"
    driver.write_text('import runpy, sys, urllib.request\nfrom pathlib import Path\nsys.path.insert(0,str(Path(sys.argv[1]).parent))\nclass Response:\n status=200\n def __enter__(self): return self\n def __exit__(self,*args): pass\ndef request(*args,**kwargs):\n print("CHECK_IN")\n return Response()\nurllib.request.urlopen=request\nrunpy.run_path(sys.argv[1],run_name="__main__")\n')
    url = "https://nosnch.in/system-test-fixture"
    environment = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"], GITHUB_REPOSITORY="example/catalog", GITHUB_EVENT_PATH=str(event), DMS_CHECK_IN_URL=url)
    for run_id, conclusion, secret, success, checked_in in (
        (9, "success", url, True, True),
        (8, "success", url, True, False),
        (9, "failure", url, True, False),
        (9, "success", "", False, False),
        (9, "success", "http://nosnch.in/system-test-fixture", False, False),
        (9, "success", "https://example.com/system-test-fixture", False, False),
    ):
        event.write_text(json.dumps({"workflow_run": {"id": run_id, "conclusion": conclusion}}))
        result = subprocess.run([sys.executable, str(driver), str(ROOT / "scripts/heartbeat.py")], env=environment | {"DMS_CHECK_IN_URL": secret}, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stderr
        assert ("CHECK_IN" in result.stdout) == checked_in
        assert url not in result.stdout + result.stderr

print("System heartbeat: latest successful refresh only, stale/failing runs ignored, secret URL validation, no URL logging passed")
