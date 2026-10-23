"""Google Health API v4 OAuth and read-only daily dashboard adapter."""

import asyncio
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx


SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
]
API_BASE = "https://health.googleapis.com/v4/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
LOCAL_TIMEZONE = ZoneInfo("Asia/Bangkok")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_project_env() -> None:
    """Load only the two OAuth values from the project's local, ignored .env."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"} and key not in os.environ:
            os.environ[key] = json.loads(value.strip())


load_project_env()


class HealthAPIError(Exception):
    def __init__(self, status: int, reason: str):
        self.status = status
        self.reason = reason
        super().__init__(f"Google Health API returned {status}: {reason}")


class GoogleHealthConnection:
    def __init__(self) -> None:
        self.tokens: dict | None = None
        self.expires_at: datetime | None = None
        self._refresh_lock = asyncio.Lock()
        self._cache: dict[int, tuple[datetime, dict]] = {}

    @property
    def configured(self) -> bool:
        return bool((os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET")) or os.getenv("GOOGLE_OAUTH_CREDENTIALS"))

    @property
    def connected(self) -> bool:
        return self.tokens is not None

    def credentials(self) -> dict:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if client_id and client_secret:
            return {"client_id": client_id, "client_secret": client_secret}
        path = os.getenv("GOOGLE_OAUTH_CREDENTIALS")
        if not path:
            raise RuntimeError("Google OAuth credentials are not configured")
        data = json.loads(Path(path).read_text())
        client = data.get("web")
        if not client or not client.get("client_id") or not client.get("client_secret"):
            raise RuntimeError("Credentials file must contain a web OAuth client")
        return client

    def disconnect(self) -> None:
        self.tokens = None
        self.expires_at = None
        self._cache.clear()

    def save_tokens(self, payload: dict) -> None:
        if not payload.get("access_token"):
            raise ValueError("OAuth response had no access token")
        if not payload.get("refresh_token") and not (self.tokens or {}).get("refresh_token"):
            raise ValueError("OAuth response had no refresh token")
        self.tokens = {**(self.tokens or {}), **payload}
        self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, int(payload.get("expires_in", 3600)) - 60))
        self._cache.clear()

    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        client = self.credentials()
        async with httpx.AsyncClient(timeout=20) as http:
            response = await http.post(TOKEN_URL, data={
                "code": code,
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            })
        if response.status_code != 200:
            raise HealthAPIError(response.status_code, "TOKEN_EXCHANGE_FAILED")
        return response.json()

    async def access_token(self) -> str:
        if not self.tokens:
            raise HealthAPIError(401, "NOT_CONNECTED")
        if self.expires_at and datetime.now(timezone.utc) < self.expires_at:
            return self.tokens["access_token"]
        async with self._refresh_lock:
            if self.expires_at and datetime.now(timezone.utc) < self.expires_at:
                return self.tokens["access_token"]
            client = self.credentials()
            async with httpx.AsyncClient(timeout=20) as http:
                response = await http.post(TOKEN_URL, data={
                    "refresh_token": self.tokens["refresh_token"],
                    "client_id": client["client_id"],
                    "client_secret": client["client_secret"],
                    "grant_type": "refresh_token",
                })
            if response.status_code != 200:
                self.disconnect()
                raise HealthAPIError(response.status_code, "TOKEN_REFRESH_FAILED")
            self.save_tokens(response.json())
            return self.tokens["access_token"]

    async def api(self, method: str, path: str, *, params: dict | None = None, body: dict | None = None) -> dict:
        token = await self.access_token()
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.request(method, f"{API_BASE}{path}", params=params, json=body, headers={
                "Authorization": f"Bearer {token}", "Accept": "application/json",
            })
        if response.status_code >= 400:
            try:
                reason = response.json().get("error", {}).get("status", "API_ERROR")
            except ValueError:
                reason = "API_ERROR"
            raise HealthAPIError(response.status_code, reason)
        return response.json()

    async def list_points(self, data_type: str, filter_text: str, page_size: int) -> list[dict]:
        points = []
        params = {"filter": filter_text, "pageSize": page_size}
        while True:
            response = await self.api("GET", f"/dataTypes/{data_type}/dataPoints", params=params)
            points.extend(response.get("dataPoints", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return points
            params["pageToken"] = page_token

    async def reconciled_points(self, data_type: str, filter_text: str, page_size: int) -> list[dict]:
        points = []
        params = {
            "filter": filter_text,
            "pageSize": page_size,
            "dataSourceFamily": "users/me/dataSourceFamilies/google-sources",
        }
        while True:
            response = await self.api("GET", f"/dataTypes/{data_type}/dataPoints:reconcile", params=params)
            points.extend(response.get("dataPoints", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return points
            params["pageToken"] = page_token

    async def daily_rollup(self, data_type: str, start: date, end: date) -> list[dict]:
        def civil(day: date) -> dict:
            return {"date": {"year": day.year, "month": day.month, "day": day.day}}

        result = await self.api("POST", f"/dataTypes/{data_type}/dataPoints:dailyRollUp", body={
            "range": {"start": civil(start), "end": civil(end)}, "windowSizeDays": 1,
        })
        return result.get("rollupDataPoints", [])

    async def dashboard(self, days: int) -> dict:
        now = datetime.now(LOCAL_TIMEZONE)
        cached = self._cache.get(days)
        if cached and (now - cached[0]).total_seconds() < 300:
            return cached[1]
        today = now.date()
        start = today - timedelta(days=days - 1)
        end = today + timedelta(days=1)
        step_rows = await self.daily_rollup("steps", start, end)
        calorie_rows = []
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=14), end)
            calorie_rows.extend(await self.daily_rollup("total-calories", cursor, chunk_end))
            cursor = chunk_end
        hr_filter = f'daily_resting_heart_rate.date >= "{start}" AND daily_resting_heart_rate.date < "{end}"'
        sleep_filter = f'sleep.interval.civil_end_time >= "{start}" AND sleep.interval.civil_end_time < "{end}"'
        heart_rows = await self.list_points("daily-resting-heart-rate", hr_filter, 1000)
        sleep_rows = await self.reconciled_points("sleep", sleep_filter, 25)
        # A small unfiltered read distinguishes an empty account from a filter/source issue.
        sleep_probe = []
        if not sleep_rows:
            try:
                probe = await self.api("GET", "/dataTypes/sleep/dataPoints", params={"pageSize": 25})
                sleep_probe = probe.get("dataPoints", [])
                sleep_rows = sleep_probe
            except HealthAPIError:
                pass
        result = normalize_dashboard(today, days, step_rows, calorie_rows, heart_rows, sleep_rows)
        result["sleep_diagnostics"] = {
            "reconciled_sessions": len(sleep_rows) - len(sleep_probe),
            "unfiltered_sessions": len(sleep_probe),
            "sessions_with_wake_date": sum(sleep_end_date(row.get("sleep", {})) is not None for row in sleep_rows),
            "sessions_with_minutes_asleep": sum(row.get("sleep", {}).get("summary", {}).get("minutesAsleep") is not None for row in sleep_rows),
            "displayed_days": sum(day["sleep_minutes"] is not None for day in result["days"]),
        }
        result["last_synced"] = now.isoformat()
        self._cache[days] = (now, result)
        return result


def civil_date(value: dict | None) -> str | None:
    if not value:
        return None
    source = value.get("date", value)
    try:
        return date(int(source["year"]), int(source["month"]), int(source["day"])).isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def sleep_end_date(point: dict) -> str | None:
    interval = point.get("interval", {})
    civil = civil_date(interval.get("civilEndTime"))
    if civil:
        return civil
    physical = interval.get("endTime")
    if not physical:
        return None
    try:
        end = datetime.fromisoformat(physical.replace("Z", "+00:00"))
        offset = float(interval.get("endUtcOffset", "0s").removesuffix("s"))
        return (end + timedelta(seconds=offset)).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def normalize_dashboard(today: date, days: int, steps: list[dict], calories: list[dict], heart: list[dict], sleep: list[dict]) -> dict:
    entries = {}
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        entries[day.isoformat()] = {"date": day.isoformat(), "steps": None, "calories": None, "resting_heart_rate": None, "sleep_minutes": None}

    for row in steps:
        day = civil_date(row.get("civilStartTime"))
        if day in entries and row.get("steps", {}).get("countSum") is not None:
            entries[day]["steps"] = int(row["steps"]["countSum"])
    for row in calories:
        day = civil_date(row.get("civilStartTime"))
        if day in entries and row.get("totalCalories", {}).get("kcalSum") is not None:
            entries[day]["calories"] = round(float(row["totalCalories"]["kcalSum"]))
    for row in heart:
        point = row.get("dailyRestingHeartRate", {})
        day = civil_date(point.get("date"))
        if day in entries and point.get("beatsPerMinute") is not None:
            entries[day]["resting_heart_rate"] = int(point["beatsPerMinute"])
    for row in sleep:
        point = row.get("sleep", {})
        day = sleep_end_date(point)
        minutes = point.get("summary", {}).get("minutesAsleep")
        if day in entries and minutes is not None:
            current = entries[day]["sleep_minutes"]
            is_main = point.get("metadata", {}).get("mainSleep", False)
            if current is None or is_main or int(minutes) > current:
                entries[day]["sleep_minutes"] = int(minutes)
    return {"source": "google_health", "as_of": today.isoformat(), "timezone": "Asia/Bangkok", "days": list(entries.values())}


connection = GoogleHealthConnection()
