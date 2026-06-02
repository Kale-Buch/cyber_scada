from flask import Flask, jsonify, request, render_template
import os
import subprocess
import sys
import threading

app = Flask(__name__)

attack_lock = threading.Lock()
attack_processes = []

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
        proc = subprocess.Popen(cmd, cwd=os.path.dirname(__file__), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with attack_lock:
            attack_processes.append(proc)
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

    print(f"[attack_app] run_attack called: {attack_name} target={ip_addr}:{port} endpoint={endpoint}")

    if attack_name == 'brute_force':
        threading.Thread(target=run_bruteforce_attack, daemon=True).start()
        message = 'Brute force attack started in background.'
    elif attack_name in ('thread_pool_wait_starvation', 'unlimited_condition_refresh'):
        threading.Thread(target=run_exploit_framework_attack, args=(attack_name, server_type, ip_addr, port, endpoint), daemon=True).start()
        message = f'{attack_name.replace("_", " ").title()} attack started in background.'
    else:
        print(f"[attack_app] Unknown attack type: {attack_name}")
        return jsonify({'success': False, 'error': 'Unknown attack'}), 400

    return jsonify({'success': True, 'message': message})


def stop_attacks():
    stopped_any = False

    try:
        import brute_force
        if not brute_force.FOUND:
            brute_force.FOUND = True
        stopped_any = True
    except Exception:
        pass

    with attack_lock:
        for proc in attack_processes[:]:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=3)
                    except Exception:
                        pass
                stopped_any = True
        attack_processes.clear()

    return stopped_any


@app.route('/stop-attack', methods=['POST'])
def stop_attack():
    print('[attack_app] stop_attack called')
    if stop_attacks():
        return jsonify({'success': True, 'message': 'Attack interrupt requested.'})
    return jsonify({'success': False, 'message': 'No running attack found.'}), 404


@app.route('/')
def home():
    return render_template('attack_dashboard.html')


if __name__ == '__main__':
    try:
        app.run(debug=True, port=5001, use_reloader=False)
    except KeyboardInterrupt:
        print('\n[attack_app] Keyboard interrupt received, shutting down...')
        sys.exit(0)

