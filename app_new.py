from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from opcua import Client
import sqlite3
import os
import threading
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "database.db")

OPC_URL = os.environ.get("OPC_URL", "opc.tcp://127.0.0.1:4840/freeopcua/server/")
NS_URI = "http://scada.control"

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "super_secret_key_change_this"

client = Client(OPC_URL)
lock = threading.Lock()
opc_cache = {}
ALL_NODES = {}
opc_connected = False


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", ("TTU", "12345678"))
    conn.commit()
    conn.close()


def q(nsidx, name):
    return f"{nsidx}:{name}"


def connect_opc(max_attempts=20, delay_s=0.5):
    """Connect to the local OPC UA server and bind the dashboard nodes.

    The original app crashed if the server was not already reachable.  For demo use,
    this retries and prints clear messages instead of failing with a NoneType socket error.
    """
    global opc_connected, ALL_NODES

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"Connecting to OPC UA server ({attempt}/{max_attempts}): {OPC_URL}")
            client.connect()

            nsidx = client.get_namespace_index(NS_URI)
            print(f"Connected to OPC UA server. Namespace index is: {nsidx}")

            objects = client.get_objects_node()
            dashboard = objects.get_child([q(nsidx, "Dashboard_Interface")])

            load_obj = dashboard.get_child([q(nsidx, "LOAD")])
            source_obj = dashboard.get_child([q(nsidx, "ENERGY SOURCE")])
            battery_obj = dashboard.get_child([q(nsidx, "BATTERY")])
            inverter_obj = dashboard.get_child([q(nsidx, "LOAD INVERTER")])

            ALL_NODES = {
                "load_sw": load_obj.get_child([q(nsidx, "load_sw")]),
                "load_val": load_obj.get_child([q(nsidx, "load_val")]),
                "source_sw": source_obj.get_child([q(nsidx, "source_sw")]),
                "source_val": source_obj.get_child([q(nsidx, "source_val")]),
                "batt_sw": battery_obj.get_child([q(nsidx, "batt_sw")]),
                "batt_val": battery_obj.get_child([q(nsidx, "batt_val")]),
                "inv_sw": inverter_obj.get_child([q(nsidx, "inv_sw")]),
                "inv_val": inverter_obj.get_child([q(nsidx, "inv_val")]),
            }

            opc_connected = True
            return True

        except Exception as e:
            last_error = e
            try:
                client.disconnect()
            except Exception:
                pass
            time.sleep(delay_s)

    print(f"OPC connection failed after {max_attempts} attempts: {last_error}")
    print("Start server.py first, then run app_new.py in a second terminal.")
    return False


def poll_opc():
    while True:
        if not opc_connected:
            time.sleep(0.5)
            continue

        try:
            with lock:
                for name, node in ALL_NODES.items():
                    try:
                        opc_cache[name] = node.get_value()
                    except Exception as node_error:
                        print(f"Polling error on {name}: {node_error}")
        except Exception as e:
            print("Polling loop error:", e)

        time.sleep(0.5)


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "")
    password = data.get("password", "")

    conn = sqlite3.connect(DB_PATH)

    # Intentionally vulnerable for the teammate's security demo.
    # Do not ship this to production.
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    user = conn.execute(query).fetchone()
    conn.close()

    if user:
        session["logged_in"] = True
        return jsonify({"success": True})

    return jsonify({"success": False}), 401


@app.route("/")
def home():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("home"))
    return render_template("control_dashboard.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/data")
def get_data():
    return jsonify(opc_cache)


@app.route("/health")
def health():
    return jsonify({
        "flask": "ok",
        "opc_connected": opc_connected,
        "opc_url": OPC_URL,
        "known_nodes": sorted(ALL_NODES.keys()),
        "cache": opc_cache,
    })


@app.route("/toggle", methods=["POST"])
def toggle():
    data = request.json or {}
    name = data.get("node")

    if name not in ALL_NODES:
        return jsonify({"success": False, "error": f"unknown node: {name}"}), 400

    try:
        with lock:
            node = ALL_NODES[name]
            current_value = node.get_value()
            new_value = not bool(current_value)
            node.set_value(new_value)
            opc_cache[name] = new_value

        return jsonify({"success": True, "node": name, "new_value": new_value})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    connect_opc()
    threading.Thread(target=poll_opc, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
