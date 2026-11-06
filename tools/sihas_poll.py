"""Read-only SiHAS poll: dump all 64 holding registers. Function code 0x03 only.

    python3 tools/sihas_poll.py <device ip> [poll|scan]
"""
import socket, sys, time

PORT = 502
_pid = 0

def hdr(dlen):
    global _pid
    _pid = (_pid % 0xFF) + 1
    h = _pid.to_bytes(2,"big") + b"\x00\x00" + dlen.to_bytes(2,"big")
    return h + (sum(h) & 0xFF).to_bytes(1,"big")

def poll_pkt():
    return hdr(6) + b"\x03" + (0).to_bytes(2,"big") + (64).to_bytes(2,"big")

def scan_pkt(t="XXX", mac="???"):
    return f"SiHAS_{t}_{mac}".encode()

def send(data, ip, timeout=1.5, retry=4):
    for _ in range(retry):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(timeout)
            try:
                s.sendto(data, (ip, PORT))
                return s.recv(1024)
            except socket.timeout:
                continue
    return None

def regs(p):
    return [int.from_bytes(p[9+i*2:11+i*2],"big") for i in range(64)]

if __name__ == "__main__":
    ip = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv)>2 else "poll"
    if mode == "scan":
        r = send(scan_pkt(), ip)
        print("scan resp:", r)
        sys.exit()
    r = send(poll_pkt(), ip)
    if r is None:
        print("TIMEOUT"); sys.exit(1)
    print(f"len={len(r)} header={r[:9].hex()} fc=0x{r[7]:02x}")
    if r[7] & 8:
        print("NAK: modbus not enabled"); sys.exit(1)
    v = regs(r)
    for i in range(0, 64, 8):
        print(f"{i:02d}-{i+7:02d}: " + " ".join(f"{x:5d}" for x in v[i:i+8]))
