# Daily Pulse


## Run locally

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open <http://localhost:8765>. The charts support 7-day and 30-day views.

## Connect Google Health

1. Follow [Google's setup guide](https://developers.google.com/health/setup) to enable the Google Health API and create an OAuth client for a **web application**. If your OAuth app is in testing, add your Google Account as a test user.
2. Add `http://localhost:8765/auth/google/callback` to the client's **Authorized redirect URIs**.
3. Configure these read-only scopes:
   - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
   - `https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly`
   - `https://www.googleapis.com/auth/googlehealth.sleep.readonly`
4. Copy `.env.example` to `.env` and fill in `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` from your OAuth client.
5. Run the app, open <http://localhost:8765>, and click **Connect Google Health**.

Your device data must sync to the Google Health account you connect. The `.env` file is ignored by Git and should stay on your machine. OAuth tokens are kept in memory, so you need to reconnect after restarting the server. This local prototype supports one connected account and one server process.

## API and checks

- `GET /api/summary?date=YYYY-MM-DD` — daily metrics.
- `GET /api/trends?days=7` — trend data (1–30 days).
- `GET /api/charts/steps.svg?days=7` — example server-rendered chart.
- `uv run pytest` — run the API and sample-data tests.
