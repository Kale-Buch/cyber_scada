from flask import Flask, jsonify, request, render_template, session, redirect, url_for
import os
import subprocess
import sys
import threading

app = Flask(__name__)
# Use same secret key as main app for session sharing
app.secret_key = 'super_secret_key_change_this'

# ----------------------------
# Attack Helper Functions
# ----------------------------

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


# ----------------------------
# Routes
# ----------------------------

@app.route('/run-attack', methods=['POST'])
def run_attack():
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

@app.route("/")
def home():
    return render_template("attack_dashboard.html")


if __name__ == '__main__':
    app.run(debug=True, port=5001, use_reloader=False)

