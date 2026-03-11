"""
╔══════════════════════════════════════════════════════════════════╗
║         MY OTP API SERVER — compatibile con TGVoIP style        ║
║                                                                  ║
║  pip install flask requests                                      ║
║                                                                  ║
║  ENDPOINT:                                                       ║
║  GET /api/request?action=available_countries&apiKey=TUA_KEY      ║
║  GET /api/request?action=getNumber&apiKey=TUA_KEY&country_code=IT║
║  GET /api/request?action=getCode&apiKey=TUA_KEY&number=+39...    ║
║                                                                  ║
║  ADMIN (solo da localhost):                                      ║
║  GET /admin/keys              → lista chiavi                     ║
║  POST /admin/keys/create      → crea nuova chiave                ║
║  POST /admin/keys/delete      → elimina chiave                   ║
║  POST /admin/keys/toggle      → attiva/disattiva chiave          ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sqlite3
import secrets
import time
import logging
import requests
from flask import Flask, request, jsonify

# ─────────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────────

# Metti questa chiave su Render nelle Environment Variables
SPIDER_API_KEY = os.environ.get("SPIDER_API_KEY", "")

# Base URL di Spider Service
SPIDER_BASE_URL = "https://www.spider-service.com/api"

# Porta e host
SERVER_PORT = int(os.environ.get("PORT", 5000))
SERVER_HOST = "0.0.0.0"

# File database SQLite
DB_FILE = "myapi.db"

# Numero massimo di richieste per chiave al minuto
RATE_LIMIT = 60

# ─────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("myapi.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────────────────────────
def dbc():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with dbc() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT UNIQUE NOT NULL,
            label       TEXT DEFAULT '',
            active      INTEGER DEFAULT 1,
            balance     REAL DEFAULT 0.0,
            total_reqs  INTEGER DEFAULT 0,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS request_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key     TEXT NOT NULL,
            action      TEXT NOT NULL,
            country     TEXT DEFAULT '',
            number      TEXT DEFAULT '',
            success     INTEGER DEFAULT 1,
            ip          TEXT DEFAULT '',
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS rate_limit (
            api_key      TEXT PRIMARY KEY,
            count        INTEGER DEFAULT 0,
            window_start INTEGER DEFAULT 0
        );
        """)
    log.info("Database inizializzato.")

# ─────────────────────────────────────────────────────────────────
#  API KEY HELPERS
# ─────────────────────────────────────────────────────────────────
def generate_key(label: str = "") -> str:
    key = "myapi_" + secrets.token_hex(16)
    with dbc() as c:
        c.execute(
            "INSERT INTO api_keys (key, label) VALUES (?, ?)",
            (key, label)
        )
    log.info(f"Nuova API key creata: {key[:12]}... label={label}")
    return key

def get_key(key: str):
    with dbc() as c:
        return c.execute(
            "SELECT * FROM api_keys WHERE key=? AND active=1", (key,)
        ).fetchone()

def check_rate_limit(key: str) -> bool:
    now = int(time.time())
    with dbc() as c:
        r = c.execute(
            "SELECT count, window_start FROM rate_limit WHERE api_key=?", (key,)
        ).fetchone()
        if not r:
            c.execute(
                "INSERT INTO rate_limit (api_key, count, window_start) VALUES (?,1,?)",
                (key, now)
            )
            return True

        count, window_start = r["count"], r["window_start"]

        if now - window_start > 60:
            c.execute(
                "UPDATE rate_limit SET count=1, window_start=? WHERE api_key=?",
                (now, key)
            )
            return True

        if count >= RATE_LIMIT:
            return False

        c.execute(
            "UPDATE rate_limit SET count=count+1 WHERE api_key=?", (key,)
        )
        return True

def log_request(key: str, action: str, country="", number="", success=True, ip=""):
    with dbc() as c:
        c.execute(
            "INSERT INTO request_log (api_key, action, country, number, success, ip)"
            " VALUES (?,?,?,?,?,?)",
            (key, action, country, number, 1 if success else 0, ip)
        )
        c.execute(
            "UPDATE api_keys SET total_reqs=total_reqs+1 WHERE key=?", (key,)
        )

# ─────────────────────────────────────────────────────────────────
#  SPIDER SERVICE
# ─────────────────────────────────────────────────────────────────
def spider_req(endpoint: str, params: dict) -> dict:
    if not SPIDER_API_KEY:
        return {"status": "error", "detail": "SPIDER_API_KEY non configurata"}

    try:
        r = requests.get(
            f"{SPIDER_BASE_URL}/{endpoint}",
            params={"api_key": SPIDER_API_KEY, **params},
            timeout=20
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"status": "error", "detail": "Spider timeout"}
    except requests.exceptions.ConnectionError:
        return {"status": "error", "detail": "Spider non raggiungibile"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

def spider_countries() -> dict:
    res = spider_req("countries", {})
    out = {}
    try:
        items = res.get("countries") or res.get("data") or []
        for item in items:
            if isinstance(item, dict):
                code = str(item.get("code", item.get("country", ""))).upper()
                price = float(item.get("price", item.get("cost", 1.0)))
                if code and len(code) == 2:
                    out[code] = price
            elif isinstance(item, str):
                out[item.upper()] = 1.0
    except Exception as e:
        log.warning(f"spider_countries parse error: {e} — res: {res}")
    return out

def spider_get_number(country_code: str) -> dict:
    res = spider_req("buy", {"country": country_code})

    ok = (
        res.get("status") == "ok" or
        res.get("success") is True or
        res.get("success") == "true"
    )

    if ok:
        number = str(res.get("number", res.get("phone", ""))).strip()
        price = float(res.get("price", res.get("cost", 1.0)))
        order_id = str(res.get("id", res.get("order_id", res.get("activationId", ""))))
        if number and number not in ("", "null", "None", "0"):
            return {
                "status": "ok",
                "number": number,
                "price": price,
                "order_id": order_id
            }

    detail = (res.get("detail") or res.get("error") or res.get("message") or str(res))[:300]
    return {"status": "error", "detail": detail}

def spider_get_code(number: str, order_id: str = "") -> dict:
    params = {"number": number}
    if order_id:
        params["id"] = order_id

    res = spider_req("code", params)
    code = str(res.get("code", res.get("sms", res.get("otp", "")))).strip()

    if code and code not in ("", "null", "None", "0", "false"):
        return {"status": "ok", "code": code}

    if res.get("status") == "error":
        return {"status": "error", "detail": res.get("detail", "Spider error")}

    return {"status": "waiting", "code": ""}

# ─────────────────────────────────────────────────────────────────
#  FLASK APP
# ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

# Inizializza DB anche quando parte con gunicorn
init_db()

# Crea automaticamente una prima API key se il DB è vuoto
try:
    with dbc() as c:
        n = c.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    if n == 0:
        first_key = generate_key("default")
        log.info(f"Prima API key creata automaticamente: {first_key}")
except Exception as e:
    log.error(f"Errore inizializzazione chiave default: {e}")

# Cache paesi
_countries_cache = {"data": {}, "ts": 0}

def get_countries_cached() -> dict:
    now = time.time()
    if now - _countries_cache["ts"] > 600:
        fresh = spider_countries()
        if fresh:
            _countries_cache["data"] = fresh
            _countries_cache["ts"] = now
            log.info(f"Countries aggiornati: {len(fresh)} paesi")
    return _countries_cache["data"]

# ─────────────────────────────────────────────────────────────────
#  MIDDLEWARE
# ─────────────────────────────────────────────────────────────────
def verify_key(api_key: str) -> tuple:
    if not api_key:
        return False, {"status": "error", "detail": "apiKey mancante"}

    row = get_key(api_key)
    if not row:
        return False, {"status": "error", "detail": "apiKey non valida o disattivata"}

    if not check_rate_limit(api_key):
        return False, {"status": "error", "detail": f"Rate limit superato ({RATE_LIMIT} req/min)"}

    return True, row

# ─────────────────────────────────────────────────────────────────
#  ENDPOINT PRINCIPALE
# ─────────────────────────────────────────────────────────────────
@app.route("/api/request", methods=["GET"])
def api_request():
    api_key = request.args.get("apiKey", "").strip()
    action = request.args.get("action", "").strip()
    ip = request.remote_addr or ""

    ok, result = verify_key(api_key)
    if not ok:
        log.warning(f"Chiave non valida da {ip}: {api_key[:12] if api_key else 'VUOTA'}")
        return jsonify(result), 403

    if action == "available_countries":
        countries = get_countries_cached()
        if not countries:
            log_request(api_key, action, success=False, ip=ip)
            return jsonify({
                "status": "error",
                "detail": "Nessun paese disponibile al momento"
            }), 503

        log_request(api_key, action, success=True, ip=ip)
        log.info(f"[{api_key[:10]}] available_countries → {len(countries)} paesi")
        return jsonify({
            "status": "ok",
            "countries": countries
        })

    elif action == "getNumber":
        country_code = request.args.get("country_code", "").strip().upper()
        if not country_code or len(country_code) != 2:
            return jsonify({
                "status": "error",
                "detail": "country_code mancante o non valido (es: IT, US, DE)"
            }), 400

        res = spider_get_number(country_code)
        success = (res["status"] == "ok")
        log_request(api_key, action, country=country_code, success=success, ip=ip)

        if success:
            log.info(f"[{api_key[:10]}] getNumber {country_code} → {res['number'][:6]}***")
            return jsonify({
                "status": "ok",
                "Number": res["number"],
                "price": res["price"],
                "order_id": res["order_id"],
                "hash_code": res["number"]
            })
        else:
            log.warning(f"[{api_key[:10]}] getNumber {country_code} FALLITO: {res['detail']}")
            return jsonify({
                "status": "error",
                "detail": res["detail"]
            })

    elif action == "getCode":
        number = request.args.get("number", "").strip()
        order_id = request.args.get("order_id", "").strip()

        if not number:
            return jsonify({
                "status": "error",
                "detail": "number mancante"
            }), 400

        res = spider_get_code(number, order_id)
        success = (res["status"] == "ok")
        log_request(api_key, action, number=number[:6]+"***", success=success, ip=ip)

        if success:
            log.info(f"[{api_key[:10]}] getCode {number[:6]}*** → {res['code']}")
            return jsonify({
                "status": "ok",
                "Number": number,
                "code": res["code"],
                "pass": ""
            })
        elif res["status"] == "waiting":
            return jsonify({
                "status": "ok",
                "Number": number,
                "code": "",
                "pass": ""
            })
        else:
            return jsonify({
                "status": "error",
                "detail": res.get("detail", "Errore sconosciuto")
            })

    else:
        return jsonify({
            "status": "error",
            "detail": f"Azione '{action}' non riconosciuta. Usa: available_countries, getNumber, getCode"
        }), 400

# ─────────────────────────────────────────────────────────────────
#  ENDPOINT ADMIN
# ─────────────────────────────────────────────────────────────────
def require_localhost(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if request.remote_addr not in ("127.0.0.1", "::1"):
            return jsonify({"error": "Accesso negato — solo localhost"}), 403
        return f(*args, **kwargs)
    return decorated

@app.route("/admin/keys", methods=["GET"])
@require_localhost
def admin_list_keys():
    with dbc() as c:
        rows = c.execute(
            "SELECT id, key, label, active, balance, total_reqs, created_at"
            " FROM api_keys ORDER BY created_at DESC"
        ).fetchall()

    keys = []
    for r in rows:
        masked = r["key"][:12] + "..." + r["key"][-4:]
        keys.append({
            "id": r["id"],
            "key": r["key"],
            "key_masked": masked,
            "label": r["label"],
            "active": bool(r["active"]),
            "balance": r["balance"],
            "total_reqs": r["total_reqs"],
            "created_at": time.strftime("%d/%m/%Y %H:%M", time.localtime(r["created_at"]))
        })

    return jsonify({"status": "ok", "keys": keys, "total": len(keys)})

@app.route("/admin/keys/create", methods=["POST"])
@require_localhost
def admin_create_key():
    data = request.get_json(silent=True) or {}
    label = str(data.get("label", "")).strip()[:100]
    key = generate_key(label)
    return jsonify({
        "status": "ok",
        "key": key,
        "label": label,
        "message": "Chiave creata! Salvala subito, non viene mostrata di nuovo."
    })

@app.route("/admin/keys/delete", methods=["POST"])
@require_localhost
def admin_delete_key():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip()
    if not key:
        return jsonify({"status": "error", "detail": "key mancante"}), 400

    with dbc() as c:
        c.execute("DELETE FROM api_keys WHERE key=?", (key,))
        c.execute("DELETE FROM rate_limit WHERE api_key=?", (key,))

    log.info(f"API key eliminata: {key[:12]}...")
    return jsonify({"status": "ok", "message": "Chiave eliminata."})

@app.route("/admin/keys/toggle", methods=["POST"])
@require_localhost
def admin_toggle_key():
    data = request.get_json(silent=True) or {}
    key = str(data.get("key", "")).strip()
    if not key:
        return jsonify({"status": "error", "detail": "key mancante"}), 400

    with dbc() as c:
        r = c.execute("SELECT active FROM api_keys WHERE key=?", (key,)).fetchone()
        if not r:
            return jsonify({"status": "error", "detail": "Chiave non trovata"}), 404
        new_state = 0 if r["active"] else 1
        c.execute("UPDATE api_keys SET active=? WHERE key=?", (new_state, key))

    status_label = "ATTIVATA" if new_state else "DISATTIVATA"
    log.info(f"API key {key[:12]}... {status_label}")
    return jsonify({
        "status": "ok",
        "active": bool(new_state),
        "message": f"Chiave {status_label}."
    })

@app.route("/admin/stats", methods=["GET"])
@require_localhost
def admin_stats():
    with dbc() as c:
        total_keys = c.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        active_keys = c.execute("SELECT COUNT(*) FROM api_keys WHERE active=1").fetchone()[0]
        total_reqs = c.execute("SELECT COALESCE(SUM(total_reqs),0) FROM api_keys").fetchone()[0]
        reqs_ok = c.execute("SELECT COUNT(*) FROM request_log WHERE success=1").fetchone()[0]
        reqs_fail = c.execute("SELECT COUNT(*) FROM request_log WHERE success=0").fetchone()[0]
        reqs_today = c.execute(
            "SELECT COUNT(*) FROM request_log WHERE created_at > ?",
            (int(time.time()) - 86400,)
        ).fetchone()[0]

    countries = get_countries_cached()
    return jsonify({
        "status": "ok",
        "total_keys": total_keys,
        "active_keys": active_keys,
        "total_requests": total_reqs,
        "requests_ok": reqs_ok,
        "requests_fail": reqs_fail,
        "requests_today": reqs_today,
        "countries_available": len(countries),
        "spider_key_set": bool(SPIDER_API_KEY),
    })

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "ok",
        "message": "MY OTP API SERVER online"
    })

# ─────────────────────────────────────────────────────────────────
#  AVVIO LOCALE
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  MY OTP API SERVER")
    print(f"  Host:   {SERVER_HOST}:{SERVER_PORT}")
    print(f"  Spider: {SPIDER_BASE_URL}")
    print("=" * 60)
    print(f"  Avvio server su http://{SERVER_HOST}:{SERVER_PORT} ...")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
