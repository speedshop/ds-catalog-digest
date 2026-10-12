import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    from sync_incident import gh

    run = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())["workflow_run"]
    latest = json.loads(gh("run", "list", "--repo", os.environ["GITHUB_REPOSITORY"], "--workflow", "publish.yml", "--branch", "main", "--status", "completed", "--limit", "1", "--json", "databaseId"))
    if run["conclusion"] != "success" or not latest or latest[0]["databaseId"] != run["id"]:
        return
    url = os.environ.get("DMS_CHECK_IN_URL", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "nosnch.in" or parsed.username or parsed.password or not parsed.path.strip("/"):
        raise SystemExit("Configure DMS_CHECK_IN_URL with this repository's HTTPS Dead Man's Snitch check-in URL")
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": "catalog-maintenance-heartbeat"}), timeout=15) as response:
                if not 200 <= response.status < 300:
                    raise SystemExit(f"Dead Man's Snitch check-in was not accepted (HTTP {response.status})")
                status = response.status
            print(f"Successful catalog refresh acknowledged by Dead Man's Snitch (HTTP {status})")
            return
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise SystemExit("Dead Man's Snitch check-in failed after three attempts") from None
            time.sleep(2**attempt)


if __name__ == "__main__":
    main()
