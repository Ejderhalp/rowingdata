# RowFlow – Rowing Training Tracker

A colorful and accessible exercise tracking website to log daily rowing sessions, speed, and mileage. Data is stored in a developer-friendly CSV file that can be opened in Excel.

## Features
- Accessible input form to log sessions (date, distance, duration, speed, type, notes)
- CSV storage (`data/rowing_log.csv`) with export
- Yearly table: mileage for every day of the selected year (including zero-mileage days)
- Charts (Chart.js): daily mileage, monthly totals by type, speed over time, cumulative mileage
- Simple JSON APIs for custom integrations

## Quickstart

### Prerequisites
- Python 3.10+

### Setup
```bash
cd /workspace/rowing_tracker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run
```bash
python app.py
```
The app runs at http://localhost:5000

### Production (optional)
```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:create_app
```

## Data
- Data directory: `data/`
- CSV file: `data/rowing_log.csv`
- Columns: `date, distance_km, duration_min, speed_kmh, session_type, notes, created_at`

You can back up or copy this CSV directly to open in Excel.

## APIs
- `GET /api/data` — all rows
- `GET /api/yearly_table?year=YYYY` — daily mileage and cumulative for a year
- `GET /api/monthly_totals?year=YYYY` — monthly totals by session type
- `GET /export` — download the CSV file

## Customization
- Edit styles in `static/css/styles.css`
- Edit charts in `static/js/charts.js`
- Add new session types by modifying `SESSION_TYPES` in `app.py`

## License
MIT