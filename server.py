from opcua import Server
import time
import random

OPC_ENDPOINT = "opc.tcp://0.0.0.0:4840/freeopcua/server/"
NS_URI = "http://scada.control"


def make_bool(parent, nsidx, name, initial):
    node = parent.add_variable(nsidx, name, bool(initial))
    node.set_writable()
    return node


def make_number(parent, nsidx, name, initial):
    node = parent.add_variable(nsidx, name, initial)
    node.set_writable()
    return node


def main():
    server = Server()
    server.set_endpoint(OPC_ENDPOINT)
    server.set_server_name("SCADA Dashboard Demo OPC UA Server")

    nsidx = server.register_namespace(NS_URI)
    print(f"Namespace registered: ns={nsidx}, uri={NS_URI}")

    objects = server.get_objects_node()
    dashboard = objects.add_object(nsidx, "Dashboard_Interface")

    load_obj = dashboard.add_object(nsidx, "LOAD")
    source_obj = dashboard.add_object(nsidx, "ENERGY SOURCE")
    battery_obj = dashboard.add_object(nsidx, "BATTERY")
    inverter_obj = dashboard.add_object(nsidx, "LOAD INVERTER")

    # Switch/control nodes.  These are the exact names the Flask dashboard and attack use.
    load_sw = make_bool(load_obj, nsidx, "load_sw", True)
    source_sw = make_bool(source_obj, nsidx, "source_sw", True)
    batt_sw = make_bool(battery_obj, nsidx, "batt_sw", True)
    inv_sw = make_bool(inverter_obj, nsidx, "inv_sw", True)

    # Display/telemetry nodes.
    load_val = make_number(load_obj, nsidx, "load_val", 120)
    source_val = make_number(source_obj, nsidx, "source_val", 68.5)
    batt_val = make_number(battery_obj, nsidx, "batt_val", 44.3)
    inv_val = make_number(inverter_obj, nsidx, "inv_val", 350)

    server.start()
    print(f"OPC UA server running at {OPC_ENDPOINT}")
    print("Use Ctrl+C to stop.  Keep this window open while running the dashboard and attack.")

    try:
        while True:
            # Keep telemetry visually tied to switch states so the attack is obvious on the dashboard.
            load_val.set_value(120 if load_sw.get_value() else 0)
            inv_val.set_value(350 if inv_sw.get_value() else 0)

            # Small live-looking drift while the source/battery remain online.
            source_val.set_value(round(68.5 + random.uniform(-0.3, 0.3), 1) if source_sw.get_value() else 0.0)
            batt_val.set_value(round(44.3 + random.uniform(-0.2, 0.2), 1) if batt_sw.get_value() else 0.0)

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping OPC UA server...")
        server.stop()


if __name__ == "__main__":
    main()
