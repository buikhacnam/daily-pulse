from datetime import date
from pathlib import Path
from urllib.parse import urlencode
import secrets

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .data import dashboard_data
from .charts import CHARTS, chart_svg
from .google_health import AUTHORIZE_URL, HealthAPIError, SCOPES, connection


ROOT = Path(__file__).resolve().parent
CALLBACK_URL = "http://localhost:8765/auth/google/callback"
app = FastAPI(title="Daily Pulse", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
async def index() -> HTMLResponse:
    return HTMLResponse((ROOT / "static" / "index.html").read_text())


@app.get("/api/summary")
async def summary(day: date | None = Query(default=None, alias="date")) -> dict:
    data = await get_data(30)
    selected = day or date.fromisoformat(data["as_of"])
    item = next((entry for entry in data["days"] if entry["date"] == selected.isoformat()), None)
    if item is None:
        raise HTTPException(status_code=404, detail="No data for this date")
    return {"source": data["source"], "timezone": data["timezone"], **item}


@app.get("/api/trends")
async def trends(days: int = Query(default=7, ge=1, le=30)) -> dict:
    data = await get_data(days)
    return {**data, "days": data["days"][-days:]}


@app.get("/api/charts/{metric}.svg")
async def chart(metric: str, days: int = Query(default=7, ge=1, le=30)) -> Response:
    if metric not in CHARTS:
        raise HTTPException(status_code=404, detail="Unknown chart")
    data = await get_data(days)
    return Response(chart_svg(metric, data["days"][-days:]), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


async def get_data(days: int) -> dict:
    if not connection.connected:
        return dashboard_data()
    try:
        return await connection.dashboard(days)
    except HealthAPIError as exc:
        raise HTTPException(status_code=502, detail=f"Google Health: {exc.reason}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Google Health") from exc


@app.get("/api/status")
async def status() -> dict:
    return {"configured": connection.configured, "connected": connection.connected, "storage": "memory_only"}


@app.get("/auth/google/start", include_in_schema=False)
async def auth_start(request: Request) -> RedirectResponse:
    if request.url.hostname != "localhost":
        return RedirectResponse("http://localhost:8765/auth/google/start")
    try:
        client = connection.credentials()
    except (RuntimeError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="OAuth credentials are not configured")
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": client["client_id"], "redirect_uri": CALLBACK_URL,
        "response_type": "code", "scope": " ".join(SCOPES),
        "access_type": "offline", "prompt": "consent", "state": state,
    }
    response = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}")
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax", path="/")
    return response


@app.get("/auth/google/callback", include_in_schema=False)
async def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    stored = request.cookies.get("oauth_state")
    if not stored or not state or not secrets.compare_digest(stored, state):
        raise HTTPException(status_code=400, detail="OAuth state mismatch; start connection again")
    if error or not code:
        response = RedirectResponse("/?auth=denied")
    else:
        try:
            connection.save_tokens(await connection.exchange_code(code, CALLBACK_URL))
            await connection.api("GET", "/identity")
            response = RedirectResponse("/?auth=connected")
        except (HealthAPIError, httpx.RequestError, ValueError):
            connection.disconnect()
            response = RedirectResponse("/?auth=failed")
    response.delete_cookie("oauth_state", path="/")
    return response


@app.post("/auth/disconnect")
async def disconnect(request: Request) -> dict:
    origin = request.headers.get("origin")
    if origin and origin != "http://localhost:8765":
        raise HTTPException(status_code=403, detail="Invalid origin")
    connection.disconnect()
    return {"connected": False}


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
