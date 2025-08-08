import os
import csv
import math
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import List, Dict, Any

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort


APP_TITLE = "RowFlow – Rowing Training Tracker"
DATA_DIR = os.environ.get("ROWING_TRACKER_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
CSV_PATH = os.path.join(DATA_DIR, "rowing_log.csv")
CSV_FIELDS = [
    "date",            # YYYY-MM-DD
    "distance_km",     # float
    "duration_min",    # float (optional)
    "speed_kmh",       # float (optional)
    "session_type",    # str
    "notes",           # str
    "created_at"       # ISO timestamp
]
SESSION_TYPES = ["Water", "Erg", "Cross-Training", "Strength", "Other"]


def ensure_storage_ready() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def parse_float(value: str) -> float:
    try:
        if value is None or value == "":
            return math.nan
        return float(value)
    except ValueError:
        return math.nan


def sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    # Coerce and clean inputs
    d = row.get("date", "").strip()
    try:
        # Validate/normalize date format
        parsed = datetime.strptime(d, "%Y-%m-%d").date()
        d = parsed.isoformat()
    except Exception:
        # Fall back to today if invalid
        d = date.today().isoformat()

    distance_km = parse_float(str(row.get("distance_km", "")).strip())
    duration_min = parse_float(str(row.get("duration_min", "")).strip())
    speed_kmh = parse_float(str(row.get("speed_kmh", "")).strip())

    # Backfill missing fields if possible
    if (math.isnan(speed_kmh)) and (not math.isnan(distance_km)) and (not math.isnan(duration_min)) and duration_min > 0:
        speed_kmh = distance_km / (duration_min / 60.0)
    if (math.isnan(duration_min)) and (not math.isnan(distance_km)) and (not math.isnan(speed_kmh)) and speed_kmh > 0:
        duration_min = (distance_km / speed_kmh) * 60.0

    # Clamp to reasonable precision
    def fmt_num(x: float) -> str:
        return "" if math.isnan(x) else f"{x:.2f}"

    session_type = row.get("session_type", "Other").strip() or "Other"
    if session_type not in SESSION_TYPES:
        session_type = "Other"

    notes = (row.get("notes", "") or "").strip()

    return {
        "date": d,
        "distance_km": fmt_num(distance_km),
        "duration_min": fmt_num(duration_min),
        "speed_kmh": fmt_num(speed_kmh),
        "session_type": session_type,
        "notes": notes,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def read_all_rows() -> List[Dict[str, str]]:
    ensure_storage_ready()
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
    return rows


def append_row(row: Dict[str, Any]) -> None:
    ensure_storage_ready()
    with open(CSV_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writerow(row)


def daterange(start_date: date, end_date: date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def compute_daily_mileage_by_year(rows: List[Dict[str, str]], year: int) -> Dict[str, float]:
    per_day = defaultdict(float)
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if d.year == year:
                try:
                    km = float(r.get("distance_km", "0") or 0)
                except ValueError:
                    km = 0.0
                per_day[d.isoformat()] += km
        except Exception:
            continue

    # Ensure all days present
    first = date(year, 1, 1)
    last = date(year, 12, 31)
    for d in daterange(first, last):
        per_day.setdefault(d.isoformat(), 0.0)

    return dict(sorted(per_day.items(), key=lambda x: x[0]))


def compute_monthly_totals_by_type(rows: List[Dict[str, str]], year: int) -> Dict[str, Dict[str, float]]:
    # month_str -> type -> total_km
    totals: Dict[str, Dict[str, float]] = {
        f"{m:02d}": {t: 0.0 for t in SESSION_TYPES} for m in range(1, 13)
    }
    for r in rows:
        try:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if d.year != year:
                continue
            month_key = f"{d.month:02d}"
            km = float(r.get("distance_km", "0") or 0)
            t = r.get("session_type", "Other")
            if t not in SESSION_TYPES:
                t = "Other"
            totals[month_key][t] += km
        except Exception:
            continue
    return totals


def compute_cumulative_mileage(daily_mileage: Dict[str, float]) -> List[Dict[str, Any]]:
    total = 0.0
    points: List[Dict[str, Any]] = []
    for day, km in daily_mileage.items():
        total += km
        points.append({"date": day, "km": round(total, 2)})
    return points


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.route("/")
    def index():
        this_year = date.today().year
        return render_template("index.html", app_title=APP_TITLE, year=this_year, session_types=SESSION_TYPES)

    @app.route("/log", methods=["POST"])
    def log():
        payload = sanitize_row(request.form)
        append_row(payload)
        # Redirect with a small hint for client-side toast
        target_year = request.form.get("year") or payload["date"][0:4]
        return redirect(url_for("index", saved="1", year=target_year), code=303)

    @app.route("/api/data")
    def api_data():
        rows = read_all_rows()
        return jsonify({"rows": rows})

    @app.route("/api/yearly_table")
    def api_yearly_table():
        try:
            year = int(request.args.get("year") or date.today().year)
        except Exception:
            year = date.today().year
        rows = read_all_rows()
        daily = compute_daily_mileage_by_year(rows, year)
        cumulative = compute_cumulative_mileage(daily)
        return jsonify({"year": year, "daily_mileage": daily, "cumulative": cumulative})

    @app.route("/api/monthly_totals")
    def api_monthly_totals():
        try:
            year = int(request.args.get("year") or date.today().year)
        except Exception:
            year = date.today().year
        rows = read_all_rows()
        totals = compute_monthly_totals_by_type(rows, year)
        return jsonify({"year": year, "totals": totals, "session_types": SESSION_TYPES})

    @app.route("/export")
    def export_csv():
        ensure_storage_ready()
        if not os.path.exists(CSV_PATH):
            abort(404)
        filename = f"rowing_log_{date.today().isoformat()}.csv"
        return send_file(CSV_PATH, as_attachment=True, download_name=filename, mimetype="text/csv")

    return app


if __name__ == "__main__":
    ensure_storage_ready()
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)