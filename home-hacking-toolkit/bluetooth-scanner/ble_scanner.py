#!/usr/bin/env python3
"""
Bluetooth Cihaz Avcısı
========================
Etraftaki tüm Bluetooth / BLE cihazları keşfeder,
sinyal gücünü izler ve cihaz tipini tahmin eder.

Kurulum (Termux):
  pkg install python
  pip install bleak  # BLE tarama için

Kurulum (PC):
  pip install bleak

Kullanım:
  python ble_scanner.py              # Tek tarama
  python ble_scanner.py --monitor    # Sürekli izle
  python ble_scanner.py --track XX:XX:XX:XX:XX:XX  # Tek cihazı izle
"""

import asyncio
import sys
import json
import time
from datetime import datetime
from pathlib import Path

try:
    from bleak import BleakScanner
    HAS_BLEAK = True
except ImportError:
    HAS_BLEAK = False

# Sonuç dosyası
RESULTS_FILE = Path.home() / ".ble_scan_results.json"

# Bilinen BLE servis UUID'leri
KNOWN_SERVICES = {
    "0000180d": "Kalp Atış Monitörü",
    "0000180f": "Batarya Servisi",
    "0000180a": "Cihaz Bilgisi",
    "00001812": "HID (Klavye/Fare)",
    "0000181a": "Çevre Sensörü",
    "0000181c": "Kullanıcı Verisi",
    "00001801": "Generic Attribute",
    "00001800": "Generic Access",
    "0000fe95": "Xiaomi Mi",
    "0000fee0": "Xiaomi Mi Band",
    "0000fef3": "Google/Nest",
    "0000fe9f": "Google",
    "0000fd6f": "COVID Exposure Notification",
    "0000feb9": "Samsung Accessory",
    "0000fd5a": "Samsung SmartThings",
}

# Üretici ID'leri (Bluetooth SIG)
MANUFACTURER_IDS = {
    6: "Microsoft",
    76: "Apple",
    117: "Samsung",
    224: "Google",
    256: "Xiaomi",
    301: "Huawei",
    343: "Flipper Zero",  # İlginç, değil mi? :)
    89: "Nordic Semi (IoT cihaz)",
    741: "Espressif (ESP32)",
}


def rssi_to_distance(rssi, tx_power=-59):
    """RSSI'dan yaklaşık mesafe hesapla (metre)."""
    if rssi == 0:
        return -1
    ratio = rssi / tx_power
    if ratio < 1.0:
        return ratio ** 10
    else:
        return (0.89976) * (ratio ** 7.7095) + 0.111


def rssi_bar(rssi):
    """RSSI'ı görsel bara çevir."""
    # -30 çok güçlü, -100 çok zayıf
    strength = max(0, min(10, (rssi + 100) // 7))
    return "█" * strength + "░" * (10 - strength)


def identify_device(name, service_uuids, manufacturer_data):
    """Cihaz tipini tahmin et."""
    name_lower = (name or "").lower()

    # İsme göre tahmin
    if any(k in name_lower for k in ["tv", "samsung tv", "lg tv", "webos"]):
        return "Smart TV"
    if any(k in name_lower for k in ["band", "watch", "miband", "galaxy watch"]):
        return "Akıllı Saat/Bileklik"
    if any(k in name_lower for k in ["buds", "airpod", "earphone", "headphone", "jbl", "qcy"]):
        return "Kablosuz Kulaklık"
    if any(k in name_lower for k in ["speaker", "soundbar", "boom"]):
        return "Bluetooth Hoparlör"
    if any(k in name_lower for k in ["keyboard", "mouse", "trackpad"]):
        return "Klavye/Fare"
    if any(k in name_lower for k in ["printer", "yazici"]):
        return "Yazıcı"
    if any(k in name_lower for k in ["scale", "terazi"]):
        return "Akıllı Tartı"
    if any(k in name_lower for k in ["bulb", "lamp", "light", "led"]):
        return "Akıllı Lamba"
    if any(k in name_lower for k in ["lock", "kilit"]):
        return "Akıllı Kilit"
    if "flipper" in name_lower:
        return "Flipper Zero"

    # Servis UUID'lerine göre
    for uuid in (service_uuids or []):
        uuid_short = uuid.replace("-", "")[:8].lower()
        if uuid_short in KNOWN_SERVICES:
            return KNOWN_SERVICES[uuid_short]

    # Üretici verisine göre
    for mfr_id in (manufacturer_data or {}).keys():
        if mfr_id in MANUFACTURER_IDS:
            return f"{MANUFACTURER_IDS[mfr_id]} Cihazı"

    return "Bilinmeyen"


async def scan_once(duration=10):
    """Tek seferlik BLE taraması."""
    print(f"\n╔══════════════════════════════════════════╗")
    print(f"║   BLUETOOTH CİHAZ AVCISI v1.0            ║")
    print(f"║   Home Hacking Toolkit                    ║")
    print(f"╚══════════════════════════════════════════╝")
    print(f"\n[*] BLE taranıyor ({duration} saniye)...")

    devices = await BleakScanner.discover(timeout=duration, return_adv=True)

    if not devices:
        print("[!] Hiç BLE cihaz bulunamadı")
        print("[i] Bluetooth'un açık olduğundan emin ol")
        return []

    results = []

    print(f"\n[+] {len(devices)} cihaz bulundu!\n")
    print("─" * 70)

    sorted_devices = sorted(devices.items(), key=lambda x: x[1][1].rssi, reverse=True)

    for i, (address, (device, adv_data)) in enumerate(sorted_devices):
        name = adv_data.local_name or device.name or "İsimsiz"
        rssi = adv_data.rssi
        services = adv_data.service_uuids or []
        mfr_data = adv_data.manufacturer_data or {}

        device_type = identify_device(name, services, mfr_data)
        distance = rssi_to_distance(rssi)
        bar = rssi_bar(rssi)

        result = {
            "address": address,
            "name": name,
            "rssi": rssi,
            "type": device_type,
            "distance_m": round(distance, 1),
            "services": services,
            "manufacturer_ids": list(mfr_data.keys()),
        }
        results.append(result)

        # Ekrana yazdır
        print(f"  [{i:2d}] {name[:30]:<30s}")
        print(f"       Adres   : {address}")
        print(f"       Sinyal  : {bar} {rssi} dBm (~{distance:.1f}m)")
        print(f"       Tip     : {device_type}")

        if services:
            print(f"       Servis  : {', '.join(s[:8] for s in services[:3])}")

        # Üretici bilgisi
        for mfr_id in mfr_data:
            mfr_name = MANUFACTURER_IDS.get(mfr_id, f"ID:{mfr_id}")
            data_hex = mfr_data[mfr_id].hex()[:20]
            print(f"       Üretici : {mfr_name} (data: {data_hex}...)")

        print()

    print("─" * 70)
    print(f"[+] Toplam: {len(results)} cihaz")

    # Kaydet
    scan_result = {
        "scan_time": datetime.now().isoformat(),
        "device_count": len(results),
        "devices": results
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(scan_result, f, indent=2)
    print(f"[*] Sonuçlar: {RESULTS_FILE}")

    return results


async def monitor_mode(interval=10):
    """Sürekli izleme modu - yeni cihazları bildirir."""
    print("\n[*] BLE İZLEME MODU")
    print(f"[*] Her {interval} saniyede taranacak")
    print("[*] Ctrl+C ile durdur\n")

    known = {}
    scan_count = 0

    try:
        while True:
            scan_count += 1
            devices = await BleakScanner.discover(timeout=5, return_adv=True)
            ts = datetime.now().strftime("%H:%M:%S")
            current = set()

            for address, (device, adv_data) in devices.items():
                current.add(address)
                name = adv_data.local_name or device.name or "İsimsiz"
                rssi = adv_data.rssi

                if address not in known:
                    device_type = identify_device(name, adv_data.service_uuids, adv_data.manufacturer_data)
                    print(f"[{ts}] [+] YENİ: {name:<25s} {address}  {rssi_bar(rssi)} {rssi}dBm  ({device_type})")
                    known[address] = {"name": name, "first_seen": ts, "last_rssi": rssi}
                else:
                    known[address]["last_rssi"] = rssi

            # Kaybolan cihazlar
            for addr in list(known.keys()):
                if addr not in current and known[addr].get("last_rssi") is not None:
                    print(f"[{ts}] [-] KAYIP: {known[addr]['name']:<25s} {addr}")
                    known[addr]["last_rssi"] = None

            if scan_count % 6 == 0:  # Her dakika özet
                active = sum(1 for d in known.values() if d["last_rssi"] is not None)
                print(f"[{ts}] [i] Durum: {active} aktif / {len(known)} toplam görülen")

            await asyncio.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n[*] İzleme durduruldu. Toplam {len(known)} farklı cihaz görüldü.")


async def track_device(target_address, interval=2):
    """Tek bir cihazı izle (mesafe takibi)."""
    print(f"\n[*] CİHAZ TAKİBİ: {target_address}")
    print("[*] Ctrl+C ile durdur\n")

    try:
        while True:
            devices = await BleakScanner.discover(timeout=3, return_adv=True)

            if target_address.upper() in {a.upper() for a in devices}:
                for addr, (dev, adv) in devices.items():
                    if addr.upper() == target_address.upper():
                        rssi = adv.rssi
                        dist = rssi_to_distance(rssi)
                        bar = rssi_bar(rssi)
                        ts = datetime.now().strftime("%H:%M:%S")
                        direction = "YAKINLAŞIYOR" if rssi > -60 else "UZAKTA"
                        print(f"[{ts}] {bar} {rssi:4d} dBm  ~{dist:.1f}m  {direction}")
                        break
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] [!] Cihaz görünmüyor (menzil dışı?)")

            await asyncio.sleep(interval)

    except KeyboardInterrupt:
        print("\n[*] Takip durduruldu.")


def fallback_scan():
    """bleak yoksa subprocess ile basit tarama."""
    print("[!] 'bleak' kütüphanesi bulunamadı")
    print("[*] Alternatif yöntem deneniyor...\n")

    # hcitool ile tarama (Linux)
    try:
        result = subprocess.run(
            ["hcitool", "scan", "--flush"],
            capture_output=True, text=True, timeout=15
        )
        if result.stdout.strip():
            print("[+] Klasik Bluetooth cihazlar:")
            print(result.stdout)

        # BLE tarama
        result = subprocess.run(
            ["hcitool", "lescan", "--duplicates"],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            print("[+] BLE cihazlar:")
            print(result.stdout)

    except FileNotFoundError:
        print("[!] hcitool bulunamadı")
        print("[i] Kurulum:")
        print("    Termux: pip install bleak")
        print("    Linux:  sudo apt install bluez && pip install bleak")


if __name__ == "__main__":
    import subprocess

    if not HAS_BLEAK:
        fallback_scan()
        sys.exit(1)

    args = sys.argv[1:]

    if "--monitor" in args:
        asyncio.run(monitor_mode())
    elif "--track" in args:
        addr = args[args.index("--track") + 1]
        asyncio.run(track_device(addr))
    else:
        asyncio.run(scan_once())
