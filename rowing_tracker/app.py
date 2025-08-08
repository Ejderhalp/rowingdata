import os
import csv
import math
import hashlib
from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import List, Dict, Any, Optional, Tuple, Callable

from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, abort, session
from werkzeug.security import generate_password_hash, check_password_hash


APP_TITLE = "RowFlow – Rowing Training Tracker"
DATA_DIR = os.environ.get("ROWING_TRACKER_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
LOGS_DIR = os.path.join(DATA_DIR, "logs")
USERS_CSV = os.path.join(DATA_DIR, "users.csv")
# Legacy global path (unused after per-user storage) retained for compatibility
CSV_PATH = os.path.join(DATA_DIR, "rowing_log.csv")
CSV_FIELDS = [
    "date",            # YYYY-MM-DD
    "distance_km",     # float
    "duration_min",    # float (optional)
    "speed_kmh",       # float (optional, derived)
    "session_type",    # str
    "notes",           # str
    "created_at"       # ISO timestamp
]
USER_FIELDS = ["username", "password_hash", "created_at", "storage_id"]
SESSION_TYPES = ["Water", "Erg", "Cross-Training", "Strength", "Other"]


def ensure_storage_ready() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=USER_FIELDS)
            writer.writeheader()
    # Keep legacy CSV header if present
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()


def hash_username(username: str) -> str:
    return hashlib.sha256(username.encode("utf-8")).hexdigest()


def user_log_path(username: str) -> str:
    storage_id = hash_username(username)
    user_dir = os.path.join(LOGS_DIR, storage_id)
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "rowing_log.csv")


def read_users() -> Dict[str, Dict[str, str]]:
    ensure_storage_ready()
    users: Dict[str, Dict[str, str]] = {}
    with open(USERS_CSV, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("username"):
                users[r["username"]] = r
    return users


def find_user(username: str) -> Optional[Dict[str, str]]:
    return read_users().get(username)


def add_user(username: str, password: str) -> Tuple[bool, str]:
    username = username or ""
    password = password or ""
    if username.strip() == "" or password.strip() == "":
        return False, "Username and password cannot be blank."
    users = read_users()
    if username in users:
        return False, "That username is taken."
    pwhash = generate_password_hash(password)
    storage_id = hash_username(username)
    # Initialize user log file
    log_path = user_log_path(username)
    if not os.path.exists(log_path):
        with open(log_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
    # Append to users csv
    with open(USERS_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=USER_FIELDS)
        writer.writerow({
            "username": username,
            "password_hash": pwhash,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "storage_id": storage_id,
        })
    return True, "Account created."


def get_current_username() -> Optional[str]:
    return session.get("username")


def login_required(view: Callable):
    def wrapped(*args, **kwargs):
        if not get_current_username():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    wrapped.__name__ = getattr(view, "__name__", "wrapped")
    return wrapped


def parse_float(value: str) -> float:
    try:
        if value is None or value == "":
            return math.nan
        return float(value)
    except ValueError:
        return math.nan


def sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    d = row.get("date", "").strip()
    try:
        parsed = datetime.strptime(d, "%Y-%m-%d").date()
        d = parsed.isoformat()
    except Exception:
        d = date.today().isoformat()

    distance_km = parse_float(str(row.get("distance_km", "")).strip())
    duration_min = parse_float(str(row.get("duration_min", "")).strip())

    speed_kmh = parse_float(str(row.get("speed_kmh", "")).strip())
    if math.isnan(speed_kmh) and (not math.isnan(distance_km)) and (not math.isnan(duration_min)) and duration_min > 0:
        speed_kmh = distance_km / (duration_min / 60.0)

    if (math.isnan(duration_min)) and (not math.isnan(distance_km)) and (not math.isnan(speed_kmh)) and speed_kmh > 0:
        duration_min = (distance_km / speed_kmh) * 60.0

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


def read_all_rows(username: str) -> List[Dict[str, str]]:
    ensure_storage_ready()
    path = user_log_path(username)
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
    return rows


def append_row(username: str, row: Dict[str, Any]) -> None:
    ensure_storage_ready()
    path = user_log_path(username)
    with open(path, "a", newline="") as f:
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

    first = date(year, 1, 1)
    last = date(year, 12, 31)
    for d in daterange(first, last):
        per_day.setdefault(d.isoformat(), 0.0)

    return dict(sorted(per_day.items(), key=lambda x: x[0]))


def compute_monthly_totals_by_type(rows: List[Dict[str, str]], year: int) -> Dict[str, Dict[str, float]]:
    totals: Dict[str, Dict[str, float]] = { f"{m:02d}": {t: 0.0 for t in SESSION_TYPES} for m in range(1, 13) }
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
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    @app.route("/")
    def index():
        if not get_current_username():
            return redirect(url_for("login"))
        this_year = date.today().year
        return render_template("index.html", app_title=APP_TITLE, year=this_year, session_types=SESSION_TYPES)

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        message = ""
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            ok, msg = add_user(username, password)
            if ok:
                session["username"] = username
                return redirect(url_for("index"))
            else:
                message = msg
        return render_template("auth_signup.html", app_title=APP_TITLE, message=message)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        message = ""
        if request.method == "POST":
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            user = find_user(username)
            if not user or not check_password_hash(user.get("password_hash", ""), password):
                message = "Invalid username or password."
            else:
                session["username"] = username
                next_url = request.args.get("next")
                return redirect(next_url or url_for("index"))
        return render_template("auth_login.html", app_title=APP_TITLE, message=message)

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/log", methods=["POST"])
    @login_required
    def log():
        username = get_current_username()
        payload = sanitize_row(request.form)
        append_row(username, payload)
        return redirect(url_for("index", saved="1"), code=303)

    @app.route("/api/data")
    def api_data():
        username = get_current_username()
        if not username:
            return jsonify({"error": "Unauthorized"}), 401
        rows = read_all_rows(username)
        return jsonify({"rows": rows})

    @app.route("/api/yearly_table")
    def api_yearly_table():
        username = get_current_username()
        if not username:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            year = int(request.args.get("year") or date.today().year)
        except Exception:
            year = date.today().year
        rows = read_all_rows(username)
        daily = compute_daily_mileage_by_year(rows, year)
        cumulative = compute_cumulative_mileage(daily)
        return jsonify({"year": year, "daily_mileage": daily, "cumulative": cumulative})

    @app.route("/api/monthly_totals")
    def api_monthly_totals():
        username = get_current_username()
        if not username:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            year = int(request.args.get("year") or date.today().year)
        except Exception:
            year = date.today().year
        rows = read_all_rows(username)
        totals = compute_monthly_totals_by_type(rows, year)
        return jsonify({"year": year, "totals": totals, "session_types": SESSION_TYPES})

    @app.route("/export")
    def export_csv():
        username = get_current_username()
        if not username:
            return redirect(url_for("login"))
        path = user_log_path(username)
        ensure_storage_ready()
        if not os.path.exists(path):
            abort(404)
        filename = f"rowing_log_{username}_{date.today().isoformat()}.csv"
        return send_file(path, as_attachment=True, download_name=filename, mimetype="text/csv")

    return app


if __name__ == "__main__":
    ensure_storage_ready()
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)