"""
╔══════════════════════════════════════════════════════════════════╗
║         ADMIN CLI — Gestione API Keys                           ║
║                                                                  ║
║  Uso:                                                            ║
║    python admin.py list               → lista tutte le chiavi   ║
║    python admin.py create "NomeCliente" → crea nuova chiave     ║
║    python admin.py delete myapi_XXX   → elimina chiave          ║
║    python admin.py toggle myapi_XXX   → attiva/disattiva        ║
║    python admin.py stats              → statistiche             ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys, requests

BASE = "http://127.0.0.1:5000"

def list_keys():
    r = requests.get(f"{BASE}/admin/keys").json()
    keys = r.get("keys", [])
    if not keys:
        print("Nessuna chiave presente.")
        return
    print(f"\n{'ID':<4} {'LABEL':<20} {'STATO':<10} {'RICHIESTE':<12} {'CREATA':<18}")
    print("-" * 70)
    for k in keys:
        stato = "✅ ATTIVA" if k["active"] else "❌ DISATTIVA"
        print(f"{k['id']:<4} {k['label'][:20]:<20} {stato:<10} {k['total_reqs']:<12} {k['created_at']:<18}")
        print(f"     KEY: {k['key']}")
        print()

def create_key(label=""):
    r = requests.post(f"{BASE}/admin/keys/create",
                      json={"label": label}).json()
    if r.get("status") == "ok":
        print(f"\n✅ Chiave creata!")
        print(f"   Label: {r['label']}")
        print(f"   KEY:   {r['key']}")
        print(f"\n   ⚠️  Salvala subito!")
    else:
        print(f"❌ Errore: {r}")

def delete_key(key):
    r = requests.post(f"{BASE}/admin/keys/delete",
                      json={"key": key}).json()
    print("✅ " + r.get("message", str(r)))

def toggle_key(key):
    r = requests.post(f"{BASE}/admin/keys/toggle",
                      json={"key": key}).json()
    print("✅ " + r.get("message", str(r)))

def stats():
    r = requests.get(f"{BASE}/admin/stats").json()
    print(f"\n📊 STATISTICHE API SERVER")
    print(f"   Chiavi totali:     {r.get('total_keys')}")
    print(f"   Chiavi attive:     {r.get('active_keys')}")
    print(f"   Richieste totali:  {r.get('total_requests')}")
    print(f"   Richieste ok:      {r.get('requests_ok')}")
    print(f"   Richieste fallite: {r.get('requests_fail')}")
    print(f"   Richieste oggi:    {r.get('requests_today')}")
    print(f"   Paesi disponibili: {r.get('countries_available')}")
    print(f"   Spider key:        {'✅ Configurata' if r.get('spider_key_set') else '❌ NON configurata'}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    try:
        if cmd == "list":
            list_keys()
        elif cmd == "create":
            label = args[1] if len(args) > 1 else ""
            create_key(label)
        elif cmd == "delete":
            if len(args) < 2:
                print("Uso: python admin.py delete myapi_XXX")
                sys.exit(1)
            delete_key(args[1])
        elif cmd == "toggle":
            if len(args) < 2:
                print("Uso: python admin.py toggle myapi_XXX")
                sys.exit(1)
            toggle_key(args[1])
        elif cmd == "stats":
            stats()
        else:
            print(f"Comando '{cmd}' non riconosciuto.")
            print(__doc__)
    except requests.exceptions.ConnectionError:
        print("❌ Server non raggiungibile! Avvia prima start_server.bat")
