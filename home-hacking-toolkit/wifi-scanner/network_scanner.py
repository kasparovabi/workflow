#!/usr/bin/env python3
"""
WiFi Ağ Tarayıcı - Ev Cihaz Keşfi
====================================
Evdeki WiFi ağındaki tüm cihazları bulur, üreticisini tanımlar
ve açık portlarını tarar.

Kurulum (Termux):
  pkg install python nmap
  pip install scapy netifaces

Kurulum (PC - test için):
  pip install scapy netifaces

Kullanım:
  python network_scanner.py              # Tam tarama
  python network_scanner.py --quick      # Hızlı tarama (sadece ARP)
  python network_scanner.py --ports      # Port taraması dahil
  python network_scanner.py --monitor    # Sürekli izleme modu
"""

import socket
import struct
import subprocess
import sys
import time
import json
import os
from datetime import datetime
from pathlib import Path

# ============================================
# MAC -> ÜRETİCİ VERİTABANI (yaygın olanlar)
# ============================================
OUI_DATABASE = {
    # Samsung
    "00:1A:8A": "Samsung", "14:49:E0": "Samsung", "34:23:BA": "Samsung",
    "44:4E:1A": "Samsung", "50:01:D9": "Samsung", "5C:3C:27": "Samsung",
    "78:BD:BC": "Samsung", "84:25:DB": "Samsung", "98:52:B1": "Samsung",
    "A0:82:1F": "Samsung", "BC:47:60": "Samsung", "C0:BD:D1": "Samsung",
    "F8:04:2E": "Samsung",
    # Huawei
    "00:E0:FC": "Huawei", "04:F9:38": "Huawei", "10:47:80": "Huawei",
    "20:A6:80": "Huawei", "48:46:FB": "Huawei", "5C:C3:07": "Huawei",
    "70:72:3C": "Huawei", "88:66:A5": "Huawei", "CC:A2:23": "Huawei",
    # Apple
    "00:1C:B3": "Apple", "3C:15:C2": "Apple", "68:5B:35": "Apple",
    "AC:BC:32": "Apple", "DC:A9:04": "Apple", "F0:B4:79": "Apple",
    # Xiaomi
    "04:CF:8C": "Xiaomi", "28:6C:07": "Xiaomi", "50:EC:50": "Xiaomi",
    "64:CC:2E": "Xiaomi", "78:11:DC": "Xiaomi", "B0:E2:35": "Xiaomi",
    # TP-Link
    "14:CC:20": "TP-Link", "50:C7:BF": "TP-Link", "C0:25:E9": "TP-Link",
    # LG
    "00:1C:62": "LG", "10:68:3F": "LG", "34:4D:F7": "LG",
    "58:A2:B5": "LG", "A8:23:FE": "LG",
    # Arcelik/Beko (Türkiye)
    "D8:E0:E1": "Arcelik/Beko",
    # Vestel
    "E8:B2:AC": "Vestel",
    # Amazon (Echo, Fire)
    "FC:65:DE": "Amazon", "68:54:FD": "Amazon",
    # Google
    "54:60:09": "Google", "F4:F5:D8": "Google",
    # Raspberry Pi
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    # Espressif (ESP8266/ESP32)
    "24:62:AB": "ESP32/ESP8266", "30:AE:A4": "ESP32",
    "5C:CF:7F": "ESP8266", "A4:CF:12": "ESP32",
}

# Yaygın portlar ve servisleri
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    53: "DNS", 80: "HTTP", 443: "HTTPS", 554: "RTSP (Kamera)",
    548: "AFP", 631: "IPP (Yazıcı)", 1883: "MQTT (IoT)",
    3000: "Dev Server", 3389: "RDP", 5000: "UPnP",
    5353: "mDNS", 5900: "VNC", 8008: "Chromecast",
    8080: "HTTP-Alt", 8443: "HTTPS-Alt", 8888: "HTTP-Proxy",
    9090: "Web Panel", 49152: "UPnP"
}

# Sonuç kayıt dosyası
RESULTS_FILE = Path.home() / ".network_scan_results.json"


def get_local_ip():
    """Yerel IP adresini bul."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.1"


def get_network_range(local_ip):
    """Ağ aralığını hesapla (/24 subnet)."""
    parts = local_ip.split(".")
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def get_mac_vendor(mac):
    """MAC adresinden üreticiyi tahmin et."""
    prefix = mac.upper()[:8]
    return OUI_DATABASE.get(prefix, "Bilinmeyen")


def arp_scan(network_range):
    """
    ARP taraması ile ağdaki cihazları bul.
    Root/admin gerektirmez (ping bazlı fallback var).
    """
    devices = []

    # Yöntem 1: arp-scan komutu (en iyi)
    try:
        result = subprocess.run(
            ["arp-scan", "-l", "--localnet"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                parts = line.split("\t")
                if len(parts) >= 3 and "." in parts[0]:
                    devices.append({
                        "ip": parts[0],
                        "mac": parts[1],
                        "vendor": parts[2] if len(parts) > 2 else get_mac_vendor(parts[1])
                    })
            if devices:
                return devices
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Yöntem 2: ping sweep + ARP tablosu
    print("[*] Ping sweep yapılıyor...")
    base_ip = network_range.replace(".0/24", "")

    for i in range(1, 255):
        ip = f"{base_ip}.{i}"
        try:
            subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                capture_output=True, timeout=2
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # ARP tablosunu oku
    try:
        result = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=10
        )
        # veya ip neigh
        if not result.stdout.strip():
            result = subprocess.run(
                ["ip", "neigh"], capture_output=True, text=True, timeout=10
            )

        for line in result.stdout.split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                ip = None
                mac = None
                for p in parts:
                    if "." in p and p[0].isdigit():
                        ip = p.strip("()")
                    if ":" in p and len(p) == 17:
                        mac = p
                if ip and mac and mac != "00:00:00:00:00:00":
                    devices.append({
                        "ip": ip,
                        "mac": mac,
                        "vendor": get_mac_vendor(mac)
                    })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices


def scan_port(ip, port, timeout=1):
    """Tek bir portu tara."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except (socket.error, OSError):
        return False


def scan_device_ports(ip, quick=False):
    """Bir cihazın açık portlarını tara."""
    open_ports = []
    ports_to_scan = list(COMMON_PORTS.keys()) if quick else list(range(1, 1025)) + list(COMMON_PORTS.keys())
    ports_to_scan = list(set(ports_to_scan))  # Tekrarları kaldır

    for port in sorted(ports_to_scan):
        if scan_port(ip, port, timeout=0.5):
            service = COMMON_PORTS.get(port, f"port-{port}")
            open_ports.append({"port": port, "service": service})

    return open_ports


def grab_banner(ip, port, timeout=2):
    """Port'tan banner yakala (servis tespiti)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))

        # HTTP için GET isteği gönder
        if port in (80, 8080, 8443, 3000, 9090):
            sock.send(b"GET / HTTP/1.0\r\nHost: " + ip.encode() + b"\r\n\r\n")
        else:
            sock.send(b"\r\n")

        banner = sock.recv(1024).decode("utf-8", errors="ignore").strip()
        sock.close()
        return banner[:200]  # İlk 200 karakter
    except Exception:
        return None


def identify_device_type(device):
    """Açık portlara göre cihaz tipini tahmin et."""
    ports = {p["port"] for p in device.get("open_ports", [])}

    if 554 in ports:
        return "IP Kamera"
    if 631 in ports or 9100 in ports:
        return "Yazıcı"
    if 1883 in ports:
        return "IoT Cihaz (MQTT)"
    if 8008 in ports:
        return "Chromecast/Smart TV"
    if 548 in ports:
        return "Apple Cihaz"
    if 5900 in ports:
        return "VNC Server"
    if 22 in ports and 80 not in ports:
        return "Linux/Router"
    if 80 in ports or 443 in ports:
        return "Web Arayüzlü Cihaz"
    if 23 in ports:
        return "Telnet Cihaz (GÜVENLİK RİSKİ!)"

    return "Bilinmeyen"


def print_device(device, index):
    """Cihaz bilgisini güzel formatta yazdır."""
    vendor = device.get("vendor", "Bilinmeyen")
    device_type = device.get("type", "")

    print(f"\n  [{index}] {device['ip']}")
    print(f"      MAC     : {device.get('mac', 'N/A')}")
    print(f"      Üretici : {vendor}")

    if device_type:
        print(f"      Tip     : {device_type}")

    if device.get("open_ports"):
        print(f"      Portlar :")
        for p in device["open_ports"]:
            banner = p.get("banner", "")
            extra = f" — {banner[:60]}" if banner else ""
            warning = " ⚠ GÜVENSİZ!" if p["port"] == 23 else ""
            print(f"        {p['port']:5d}/tcp  {p['service']}{extra}{warning}")

    if device.get("hostname"):
        print(f"      Hostname: {device['hostname']}")


def resolve_hostname(ip):
    """IP'den hostname çöz."""
    try:
        hostname = socket.gethostbyaddr(ip)[0]
        return hostname
    except socket.herror:
        return None


def full_scan(scan_ports=False, quick=False):
    """Tam ağ taraması."""
    local_ip = get_local_ip()
    network = get_network_range(local_ip)

    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║   AĞ TARAYICI v1.0                       ║")
    print(f"║   Home Hacking Toolkit                    ║")
    print(f"╠══════════════════════════════════════════╣")
    print(f"║   Yerel IP : {local_ip:<26s} ║")
    print(f"║   Ağ       : {network:<26s} ║")
    print(f"║   Tarih    : {datetime.now().strftime('%Y-%m-%d %H:%M'):<26s} ║")
    print(f"╚══════════════════════════════════════════╝")

    # ARP taraması
    print(f"\n[*] ARP taraması başlatılıyor ({network})...")
    devices = arp_scan(network)

    if not devices:
        print("[!] Hiç cihaz bulunamadı.")
        print("[i] İpuçları:")
        print("    - Aynı WiFi ağında olduğundan emin ol")
        print("    - Root/admin yetkisi gerekebilir")
        print("    - Termux'ta: pkg install root-repo && pkg install arp-scan")
        return

    print(f"\n[+] {len(devices)} cihaz bulundu!\n")
    print("=" * 50)

    # Her cihaz için detaylı bilgi topla
    for i, device in enumerate(devices):
        # Hostname çöz
        hostname = resolve_hostname(device["ip"])
        if hostname:
            device["hostname"] = hostname

        # Port taraması (istenmişse)
        if scan_ports:
            print(f"\r[*] Port taranıyor: {device['ip']}...", end="", flush=True)
            device["open_ports"] = scan_device_ports(device["ip"], quick=quick)

            # Banner grabbing (açık portlar için)
            for port_info in device["open_ports"]:
                banner = grab_banner(device["ip"], port_info["port"])
                if banner:
                    port_info["banner"] = banner

            # Cihaz tipini tahmin et
            device["type"] = identify_device_type(device)

        print_device(device, i)

    print(f"\n{'=' * 50}")
    print(f"[+] Tarama tamamlandı: {len(devices)} cihaz")

    # Güvenlik uyarıları
    security_issues = []
    for d in devices:
        for p in d.get("open_ports", []):
            if p["port"] == 23:
                security_issues.append(f"  ⚠ {d['ip']} - Telnet açık! (şifresiz iletişim)")
            if p["port"] == 21:
                security_issues.append(f"  ⚠ {d['ip']} - FTP açık! (şifresiz dosya transferi)")
            if p["port"] == 5900:
                security_issues.append(f"  ⚠ {d['ip']} - VNC açık! (uzak masaüstü)")

    if security_issues:
        print(f"\n[!] GÜVENLİK UYARILARI:")
        for issue in security_issues:
            print(issue)

    # Sonuçları kaydet
    results = {
        "scan_time": datetime.now().isoformat(),
        "local_ip": local_ip,
        "network": network,
        "devices": devices
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[*] Sonuçlar kaydedildi: {RESULTS_FILE}")

    return devices


def monitor_mode(interval=30):
    """
    Sürekli izleme modu.
    Yeni cihaz bağlandığında veya bir cihaz ayrıldığında bildirir.
    """
    print("\n[*] AĞ İZLEME MODU")
    print(f"[*] Her {interval} saniyede bir taranacak...")
    print("[*] Durdurmak için Ctrl+C\n")

    known_devices = set()

    try:
        while True:
            network = get_network_range(get_local_ip())
            devices = arp_scan(network)
            current_macs = set()

            for d in devices:
                mac = d.get("mac", "")
                current_macs.add(mac)

                if mac not in known_devices:
                    ts = datetime.now().strftime("%H:%M:%S")
                    vendor = d.get("vendor", "Bilinmeyen")
                    print(f"[{ts}] [+] YENİ CİHAZ: {d['ip']} ({mac}) - {vendor}")
                    known_devices.add(mac)

            # Ayrılan cihazlar
            left = known_devices - current_macs
            for mac in left:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] [-] CİHAZ AYRILDI: {mac}")
                known_devices.discard(mac)

            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[*] İzleme durduruldu. {len(known_devices)} cihaz görüldü.")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--monitor" in args:
        interval = 30
        if "--interval" in args:
            interval = int(args[args.index("--interval") + 1])
        monitor_mode(interval)
    elif "--quick" in args:
        full_scan(scan_ports=False)
    elif "--ports" in args:
        full_scan(scan_ports=True, quick=True)
    else:
        full_scan(scan_ports=True)
