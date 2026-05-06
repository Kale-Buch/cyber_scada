#!/usr/bin/env python3
from opcua import Client

OPC_URL = "opc.tcp://127.0.0.1:4840/freeopcua/server/"


def browse(node, indent=0, max_depth=6):
    if indent > max_depth:
        return
    try:
        print("  " * indent + f"{node.get_browse_name()} | {node.nodeid}")
        for child in node.get_children():
            browse(child, indent + 1, max_depth)
    except Exception as e:
        print("  " * indent + f"[browse error] {e}")


def main():
    print(f"Connecting to {OPC_URL}")
    client = Client(OPC_URL)
    try:
        client.connect()
        print("Namespaces:")
        for i, uri in enumerate(client.get_namespace_array()):
            print(f"  ns={i}: {uri}")
        print("\nObjects tree:")
        browse(client.get_objects_node())
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
