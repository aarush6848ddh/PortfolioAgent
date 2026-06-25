"""Health check HTTP endpoint for PortfolioAgent."""
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from datetime import datetime
from portfolio import get_conn
from config import HEALTH_CHECK_PORT

log = logging.getLogger("health")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        status = {"service": "PortfolioAgent", "timestamp": datetime.now().isoformat()}
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT created_at FROM agent_logs ORDER BY created_at DESC LIMIT 1")
            row = cur.fetchone()
            status["db"] = "ok"
            status["last_run"] = row[0].isoformat() if row else "never"
            cur.execute("SELECT COUNT(*) FROM agent_logs WHERE created_at::date = CURRENT_DATE")
            status["runs_today"] = cur.fetchone()[0]
            conn.close()
        except Exception as e:
            status["db"] = f"error: {e}"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, format, *args):
        pass


def start_health_check():
    """Start health check server in a background daemon thread."""
    try:
        server = HTTPServer(("0.0.0.0", HEALTH_CHECK_PORT), HealthHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        log.info(f"Health check running on port {HEALTH_CHECK_PORT}")
    except Exception as e:
        log.error(f"Failed to start health check: {e}")
