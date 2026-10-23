import asyncio
from datetime import date

import httpx

from app.data import dashboard_data
from app.charts import chart_svg
from app.google_health import GoogleHealthConnection, normalize_dashboard, sleep_end_date
from app.main import app


def get(path: str) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)

    return asyncio.run(run())


def test_demo_data_has_requested_metrics_and_chronological_dates():
    data = dashboard_data(date(2026, 10, 23))
    assert len(data["days"]) == 30
    assert data["days"][-1]["date"] == "2026-10-23"
    assert data["days"][0]["date"] == "2026-09-24"
    for day in data["days"]:
        assert all(day[key] > 0 for key in ("steps", "calories", "sleep_minutes", "resting_heart_rate"))


def test_trends_range_and_summary_date():
    seven = get("/api/trends?days=7")
    assert seven.status_code == 200
    assert len(seven.json()["days"]) == 7
    assert seven.json()["source"] == "demo"
    day = seven.json()["days"][0]["date"]
    summary = get(f"/api/summary?date={day}")
    assert summary.status_code == 200
    assert summary.json()["date"] == day
    assert summary.json()["steps"] == seven.json()["days"][0]["steps"]


def test_api_rejects_unsupported_ranges_and_dates():
    assert get("/api/trends?days=31").status_code == 422
    assert get("/api/summary?date=2020-01-01").status_code == 404


def test_page_and_health_endpoint():
    page = get("/")
    assert page.status_code == 200
    assert "/api/charts/steps.svg?days=7" in page.text
    assert "<script" not in page.text
    assert "Loading…" not in page.text
    assert get("/healthz").json() == {"status": "ok"}
    assert get("/api/status").json()["connected"] is False


def test_server_rendered_range_has_values_and_daily_details():
    page = get("/?days=30")
    data = get("/api/trends?days=30").json()
    assert page.status_code == 200
    assert f"{data['days'][-1]['steps']:,}" in page.text
    assert "/api/charts/heart.svg?days=30" in page.text
    assert page.text.count("<time>") == 120
    assert 'href="/?days=30" class="selected"' in page.text
    assert get("/?days=31").status_code == 422


def test_disconnect_form_redirects_on_local_post():
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            return await client.post("/auth/disconnect", headers={"Origin": "http://127.0.0.1:8765"})

    response = asyncio.run(run())
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_google_health_normalization_preserves_missing_data_and_sleep_wake_date():
    stamp = lambda day: {"date": {"year": 2026, "month": 10, "day": day}}
    data = normalize_dashboard(
        date(2026, 10, 23), 2,
        [{"civilStartTime": stamp(23), "steps": {"countSum": "4312"}}],
        [{"civilStartTime": stamp(23), "totalCalories": {"kcalSum": 2200.6}}],
        [{"dailyRestingHeartRate": {"date": stamp(22)["date"], "beatsPerMinute": "61"}}],
        [{"sleep": {"interval": {"civilEndTime": stamp(23)}, "summary": {"minutesAsleep": "447"}, "metadata": {"mainSleep": True}}}],
    )
    assert data["days"][0] == {"date": "2026-10-22", "steps": None, "calories": None, "resting_heart_rate": 61, "sleep_minutes": None}
    assert data["days"][1] == {"date": "2026-10-23", "steps": 4312, "calories": 2201, "resting_heart_rate": None, "sleep_minutes": 447}


def test_reconciled_points_use_google_sources_and_read_every_page():
    connection = GoogleHealthConnection()
    calls = []

    async def fake_api(method, path, *, params=None, body=None):
        calls.append((method, path, params.copy()))
        return {"dataPoints": [{"sleep": {"summary": {"minutesAsleep": "420"}}}],
                "nextPageToken": "next"} if len(calls) == 1 else {"dataPoints": [{"sleep": {"summary": {"minutesAsleep": "390"}}}]}

    connection.api = fake_api
    points = asyncio.run(connection.reconciled_points("sleep", 'sleep.interval.civil_end_time >= "2026-10-22"', 25))
    assert len(points) == 2
    assert all(path == "/dataTypes/sleep/dataPoints:reconcile" for _, path, _ in calls)
    assert calls[0][2]["dataSourceFamily"] == "users/me/dataSourceFamilies/google-sources"
    assert calls[1][2]["pageToken"] == "next"


def test_sleep_end_date_uses_device_offset_when_civil_time_is_missing():
    assert sleep_end_date({"interval": {
        "endTime": "2026-10-22T23:30:00Z", "endUtcOffset": "25200s",
    }}) == "2026-10-23"


def test_callback_rejects_missing_state():
    assert get("/auth/google/callback?code=fake&state=fake").status_code == 400


def test_python_chart_endpoint_returns_svg_for_requested_range():
    response = get("/api/charts/steps.svg?days=7")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.headers["cache-control"] == "no-store"
    assert "<svg" in response.text
    assert get("/api/charts/unknown.svg").status_code == 404


def test_chart_y_axes_show_readable_values():
    assert "<!-- 8k -->" in get("/api/charts/steps.svg?days=7").text
    assert "<!-- 7.5h -->" in get("/api/charts/sleep.svg?days=7").text
    assert "<!-- 2,400 -->" in get("/api/charts/calories.svg?days=7").text
    assert "<!-- 64 -->" in get("/api/charts/heart.svg?days=7").text


def test_python_chart_handles_missing_measurements():
    days = [{"date": "2026-10-23", "sleep_minutes": None}]
    assert "No measurements for this period" in chart_svg("sleep", days)
