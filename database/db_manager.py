"""
SQLite Database Manager
Stores all accident records, severity details, alert logs.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accidents.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS accidents (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT,
            camera_id         TEXT,
            full_address      TEXT,
            city              TEXT,
            area              TEXT,
            road              TEXT,
            region            TEXT,
            country           TEXT,
            postal            TEXT,
            latitude          REAL,
            longitude         REAL,
            maps_link         TEXT,
            landmarks         TEXT,
            severity          TEXT,
            severity_score    REAL,
            confidence        REAL,
            vehicles_involved INTEGER,
            clip_path         TEXT,
            snapshot_path     TEXT,
            alert_sent        INTEGER DEFAULT 0,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS severity_details (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            accident_id         INTEGER,
            model_confidence    REAL,
            vehicles_involved   INTEGER,
            area_coverage       REAL,
            motion_blur_score   REAL,
            overlap_score       REAL,
            frame_diff_score    REAL,
            final_score         REAL,
            FOREIGN KEY(accident_id) REFERENCES accidents(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            accident_id INTEGER,
            alert_type  TEXT,
            phone       TEXT,
            status      TEXT,
            sent_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(accident_id) REFERENCES accidents(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Database ready.")


def save_accident(data, loc, detail):
    """Save accident to DB and return accident ID."""
    import json
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        INSERT INTO accidents (
            timestamp, camera_id,
            full_address, city, area, road, region, country, postal,
            latitude, longitude, maps_link, landmarks,
            severity, severity_score, confidence,
            vehicles_involved, clip_path, snapshot_path
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["timestamp"],
        data["camera_id"],
        loc.get("full_address",""),
        loc.get("city",""),
        loc.get("area",""),
        loc.get("road",""),
        loc.get("region",""),
        loc.get("country","IN"),
        loc.get("postal",""),
        loc.get("lat", 0),
        loc.get("lon", 0),
        loc.get("maps_link",""),
        json.dumps(loc.get("landmarks", [])),
        data["severity"],
        data["severity_score"],
        data["confidence"],
        detail.get("vehicles_involved", 0),
        data.get("clip_path",""),
        data.get("snapshot_path",""),
    ))

    acc_id = c.lastrowid

    c.execute("""
        INSERT INTO severity_details (
            accident_id, model_confidence, vehicles_involved,
            area_coverage, motion_blur_score, overlap_score,
            frame_diff_score, final_score
        ) VALUES (?,?,?,?,?,?,?,?)
    """, (
        acc_id,
        detail.get("model_confidence", 0),
        detail.get("vehicles_involved", 0),
        detail.get("area_coverage", 0),
        detail.get("motion_blur_score", 0),
        detail.get("overlap_score", 0),
        detail.get("frame_diff_score", 0),
        detail.get("final_score", 0),
    ))

    conn.commit()
    conn.close()
    print(f"[DB] Accident #{acc_id} saved.")
    return acc_id


def log_alert(accident_id, alert_type, phone, status):
    conn = get_conn()
    c    = conn.cursor()
    c.execute(
        "INSERT INTO alert_log (accident_id, alert_type, phone, status) VALUES (?,?,?,?)",
        (accident_id, alert_type, phone, status)
    )
    c.execute(
        "UPDATE accidents SET alert_sent=1 WHERE id=?",
        (accident_id,)
    )
    conn.commit()
    conn.close()


def get_accidents(limit=100):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM accidents ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_accident(acc_id):
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT * FROM accidents WHERE id=?", (acc_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats():
    conn = get_conn()
    c    = conn.cursor()
    c.execute("SELECT severity, COUNT(*) as n FROM accidents GROUP BY severity")
    stats = {r["severity"]: r["n"] for r in c.fetchall()}
    c.execute("SELECT COUNT(*) as total FROM accidents")
    total = c.fetchone()["total"]
    conn.close()
    return {
        "total":    total,
        "CRITICAL": stats.get("CRITICAL", 0),
        "HIGH":     stats.get("HIGH", 0),
        "MEDIUM":   stats.get("MEDIUM", 0),
        "LOW":      stats.get("LOW", 0),
    }
