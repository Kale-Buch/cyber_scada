from flask import Flask, jsonify, request, render_template
from opcua import Client, ua
from flask import session, redirect, url_for
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import subprocess
import sys
import threading
import time

app = Flask(__name__)

OPC_URL = "opc.tcp://scadadash.local:4840/freeopcua/server/"
# OPC_URL = "opc.tcp://scadadash.local:4840/freeopcua/server/"

client = Client(OPC_URL)
DB_PATH = 'database.db'

def init_db():
    # Only create/initialize if the file doesn't exist
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create the table
        cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        
        # Add your default user
        default_user = 'TTU'
        default_pass = '12345678'

        #more defensible against brute force attacks
        # default_pass = generate_password_hash('12345678')
        
        # more defensible against sql attacks
        # cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (default_user, default_pass))

        #example victim: password' OR '1'='1
        cursor.execute(f"INSERT INTO users (username, password) VALUES ('{default_user}', '{default_pass}')")

        
        conn.commit()
        conn.close()
        print("Database initialized successfully.")
# ----------------------------
# Connect to OPC
# ----------------------------
def connect_opc():
    try:
        client.connect()
        print("Connected to OPC UA server")
    except Exception as e:
        print("OPC Connection failed:", e)

connect_opc()

# CRITICALLY VULNERABLE CODE
def register_user(new_username, new_password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # The "F-String Trap"
    # This combines the command and the data into one single string
    query = f"INSERT INTO users (username, password) VALUES ('{new_username}', '{new_password}')"
    
    cursor.execute(query)
    conn.commit()

ns_idx = client.get_namespace_index("http://scada.control")
print("Namespace index is:", ns_idx)

lock = threading.Lock()
opc_cache = {}

objects = client.get_objects_node()
dashboard = objects.get_child(["2:Dashboard_Interface"])

# Get device objects
load_obj = dashboard.get_child(["2:LOAD"])
source_obj = dashboard.get_child(["2:ENERGY SOURCE"])
battery_obj = dashboard.get_child(["2:BATTERY"])
inverter_obj = dashboard.get_child(["2:LOAD INVERTER"])

# Now get variables from inside each object
LOAD_SWITCH = load_obj.get_child(["2:load_sw"])
LOAD_POWER = load_obj.get_child(["2:load_val"])

SOLAR_SOURCE = source_obj.get_child(["2:source_sw"])
SOLAR_VOLTAGE = source_obj.get_child(["2:source_val"])

BATTERY_SWITCH = battery_obj.get_child(["2:batt_sw"])
BATTERY_VOLTAGE = battery_obj.get_child(["2:batt_val"])

INVERTER_SW = inverter_obj.get_child(["2:inv_sw"])
INVERTER_POWER = inverter_obj.get_child(["2:inv_val"])


ALL_NODES = {
    "load_sw": LOAD_SWITCH,
    "load_val": LOAD_POWER,
    "source_sw": SOLAR_SOURCE,
    "source_val": SOLAR_VOLTAGE,
    "batt_sw": BATTERY_SWITCH,
    "batt_val": BATTERY_VOLTAGE,
    "inv_sw": INVERTER_SW,
    "inv_val": INVERTER_POWER,
}
# ----------------------------
# Background Polling Thread
# ----------------------------
def poll_opc():
    while True:
        try:
            with lock:
                for name, node in ALL_NODES.items():
                    try:
                        opc_cache[name] = node.get_value()
                        #print(opc_cache)
                    except Exception as node_error:
                        print(f"Polling error on {name}:", node_error)
        except Exception as e:
            print("Polling loop error:", e)

        time.sleep(0.5)

threading.Thread(target=poll_opc, daemon=True).start()

# ----------------------------
# Routes
# ----------------------------


app.secret_key = 'super_secret_key_change_this' # Required for sessions

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    conn = sqlite3.connect(DB_PATH)
    # DANGER: f-string allows injection in both username AND password
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    
    user = conn.execute(query).fetchone()
    conn.close()

    # DANGER: Just checking if 'user' exists. 
    # An attacker using "' OR 1=1 --" will always make this True.
    if user:
        session['logged_in'] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

# def login():
#     data = request.json
#     username = data.get('username')
#     password = data.get('password')
    
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
    
#     # SECURE: '?' ensures input is treated ONLY as data, never as code
#     user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
#     conn.close()

#     # SECURE: check_password_hash prevents timing attacks and works with 
#     # encrypted versions of the password rather than plaintext.
#     if user and check_password_hash(user['password'], password):
#         session['permanent'] = True # Good practice for session management
#         session['logged_in'] = True
#         return jsonify({"success": True})
        
#     return jsonify({"success": False}), 401

@app.route("/")
def home():
    return render_template("login.html")

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('home')) # Kick them out if not logged in
    return render_template('control_dashboard.html')

@app.route('/attacks')
def attacks():
    if not session.get('logged_in'):
        return redirect(url_for('home'))
    return render_template('attack_dashboard.html')

def run_bruteforce_attack():
    try:
        import brute_force
        brute_force.FOUND = False
        brute_force.run_test()
    except Exception as e:
        print("[!] Brute force attack failed:", e)


def run_exploit_framework_attack(attack_name, server_type, ip_addr, port, endpoint):
    main_script = os.path.join(os.path.dirname(__file__), "opcua-exploit-framework", "main.py")
    if not os.path.isfile(main_script):
        print("[!] Exploit framework main.py not found")
        return

    cmd = [sys.executable, main_script, server_type, ip_addr, str(port), endpoint, attack_name]
    try:
        subprocess.Popen(cmd, cwd=os.path.dirname(__file__), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print("[!] Failed to start exploit framework attack:", e)


@app.route('/run-attack', methods=['POST'])
def run_attack():
    if not session.get('logged_in'):
        return jsonify({'success': False, 'error': 'Not logged in'}), 401

    data = request.json or {}
    attack_name = data.get('attack')
    server_type = data.get('server_type', 'prosys')
    ip_addr = data.get('ip_addr', '127.0.0.1')
    port = data.get('port', 4840)
    endpoint = data.get('endpoint', '/freeopcua/server/')

    if attack_name == 'brute_force':
        threading.Thread(target=run_bruteforce_attack, daemon=True).start()
        message = 'Brute force attack started in background.'
    elif attack_name in ('thread_pool_wait_starvation', 'unlimited_condition_refresh'):
        threading.Thread(target=run_exploit_framework_attack, args=(attack_name, server_type, ip_addr, port, endpoint), daemon=True).start()
        message = f'{attack_name.replace("_", " ").title()} attack started in background.'
    else:
        return jsonify({'success': False, 'error': 'Unknown attack'}), 400

    return jsonify({'success': True, 'message': message})

@app.route("/logout")
def logout():
    session.clear() # This actually "deletes" the login session
    return redirect(url_for('home'))

@app.route("/data")
def get_data():
    return jsonify(opc_cache)

@app.route("/toggle", methods=["POST"])
def toggle():
    name = request.json.get("node")
    try:
        with lock:
            node = ALL_NODES[name]
            current_value = node.get_value()
            new_value = not bool(current_value)

            node.set_value(new_value)
            opc_cache[name] = new_value  # instant UI update
            #checks if they are writable



        return jsonify({"success": True, "new_value": new_value})

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, use_reloader=False)