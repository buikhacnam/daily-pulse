"""Deterministic demo data, clearly separated from a future live provider."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def dashboard_data(today: date | None = None) -> dict:
    today = today or datetime.now(ZoneInfo("Asia/Bangkok")).date()
    steps = [7238, 9046, 8114, 10523, 6842, 9481, 8736, 11204, 7902, 10118, 9765, 8461, 12042, 10384, 8956, 11023, 10037, 9234, 11488, 10672, 8031, 9894, 10807, 11731, 9018, 10482, 11904, 10937, 8621, 11286]
    calories = [2160, 2388, 2251, 2552, 2103, 2430, 2338, 2641, 2212, 2520, 2467, 2275, 2780, 2599, 2354, 2651, 2490, 2406, 2684, 2547, 2270, 2453, 2533, 2712, 2384, 2587, 2750, 2621, 2328, 2694]
    sleep_minutes = [430, 472, 455, 489, 402, 461, 478, 504, 443, 481, 457, 446, 495, 469, 438, 483, 451, 474, 500, 463, 419, 478, 486, 491, 452, 475, 498, 466, 449, 482]
    resting_heart_rate = [65, 64, 66, 63, 67, 65, 64, 62, 65, 63, 64, 66, 62, 63, 65, 64, 66, 63, 62, 64, 67, 65, 63, 62, 66, 64, 63, 62, 65, 63]
    days = []
    for i in range(30):
        day = today - timedelta(days=29-i)
        days.append({
            "date": day.isoformat(),
            "steps": steps[i],
            "calories": calories[i],
            "sleep_minutes": sleep_minutes[i],
            "resting_heart_rate": resting_heart_rate[i],
        })
    return {
        "source": "demo",
        "as_of": today.isoformat(),
        "timezone": "Asia/Bangkok",
        "days": days,
    }
