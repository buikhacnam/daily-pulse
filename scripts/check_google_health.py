"""Read-only access check. Does not print or save health records or credentials."""

import getpass
import json
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


BASE = "https://health.googleapis.com/v4/users/me"


def request(path: str, token: str, params: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            body = json.load(exc)
        except (ValueError, OSError):
            body = {}
        return exc.code, body


def error_reason(body: dict) -> str:
    error = body.get("error", {})
    return error.get("status") or "API_ERROR"


def main() -> None:
    token = getpass.getpass("Paste a short-lived Google Health OAuth access token: ").strip()
    if not token:
        raise SystemExit("No token provided")
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)
    checks = {
        "steps": f'steps.interval.civil_start_time >= "{today}" AND steps.interval.civil_start_time < "{tomorrow}"',
        "heart-rate": f'heart_rate.sample_time.civil_time >= "{today}" AND heart_rate.sample_time.civil_time < "{tomorrow}"',
        "sleep": f'sleep.interval.civil_end_time >= "{yesterday}" AND sleep.interval.civil_end_time < "{tomorrow}"',
        "total-calories": f'total_calories.interval.civil_start_time >= "{today}" AND total_calories.interval.civil_start_time < "{tomorrow}"',
    }
    try:
        status, body = request("/identity", token)
        if status != 200:
            print(f"Identity: HTTP {status} ({error_reason(body)})")
            raise SystemExit(1)
        print("Identity: linked account confirmed")
        for data_type, filter_text in checks.items():
            status, body = request(f"/dataTypes/{data_type}/dataPoints", token, {"filter": filter_text, "pageSize": 1})
            if status == 200:
                state = "data available" if body.get("dataPoints") else "no records in sample window"
                print(f"{data_type}: HTTP 200 ({state})")
            else:
                print(f"{data_type}: HTTP {status} ({error_reason(body)})")
    except URLError as exc:
        raise SystemExit(f"Network error: {exc.reason}") from exc


if __name__ == "__main__":
    main()
