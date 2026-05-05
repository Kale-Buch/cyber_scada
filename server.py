from opcua import Server
import time

server = Server()
server.set_endpoint("opc.tcp://0.0.0.0:4840")

uri = "http://example.org"
idx = server.register_namespace(uri)

objects = server.get_objects_node()
myobj = objects.add_object(idx, "MyObject")
myvar = myobj.add_variable(idx, "MyVariable", 42)
myvar.set_writable()

server.start()
print("Server started at opc.tcp://localhost:4840")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    server.stop()