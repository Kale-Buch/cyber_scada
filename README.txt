SCADA Dashboard OPC UA  Control Attack Demo

Run order, using three PowerShell windows from this folder:

1) Install dependencies:
   python -m pip install -r requirements.txt

2) Start the OPC UA server:
   python server.py

3) Start the Flask dashboard:
   python app_new.py

4) Open the dashboard:
   http://127.0.0.1:5000/

   Login:
   username: TTU
   password: 12345678

5) Confirm Flask is connected to OPC UA:
   http://127.0.0.1:5000/health
   http://127.0.0.1:5000/data

6) Run the OPC UA direct-write attack in a third terminal:
   python opcua_dashboard_attack.py --restore

   Or write one node only:
   python opcua_dashboard_attack.py --node inv_sw --value off
   python opcua_dashboard_attack.py --node inv_sw --value on

Note: the attack script does not call Flask and does not use the dashboard.
It connects directly to the OPC UA server on port 4840 and writes to the same control nodes
that the Flask dashboard reads.
