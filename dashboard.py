"""
Live Dashboard — http://localhost:5000
python dashboard.py
"""

from flask import Flask, render_template, jsonify, send_file
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database.db_manager import get_accidents, get_stats, get_accident, init_db

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())

@app.route("/api/accidents")
def api_accidents():
    return jsonify({"accidents": get_accidents(50)})

@app.route("/api/clip/<int:aid>")
def api_clip(aid):
    a = get_accident(aid)
    if a and a.get("clip_path") and os.path.exists(a["clip_path"]):
        return send_file(a["clip_path"], as_attachment=True)
    return jsonify({"error": "Not found"}), 404

@app.route("/api/snapshot/<int:aid>")
def api_snapshot(aid):
    a = get_accident(aid)
    if a and a.get("snapshot_path") and os.path.exists(a["snapshot_path"]):
        return send_file(a["snapshot_path"])
    return jsonify({"error": "Not found"}), 404

if __name__ == "__main__":
    init_db()
    print("[DASHBOARD] http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
