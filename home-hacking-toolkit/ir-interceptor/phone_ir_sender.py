#!/usr/bin/env python3
"""
Telefon IR Gönderici - Huawei P40
==================================
Arduino'nun yakaladığı IR sinyalleri Huawei P40'ın
IR blaster'ı ile gönderir.

Kurulum (Termux):
  pkg install python
  pip install pyserial
  # USB OTG ile Arduino bağlıysa:
  pkg install termux-api termux-usb

Kullanım:
  python phone_ir_sender.py          # Interaktif mod
  python phone_ir_sender.py --list   # Kayıtlı sinyalleri listele
  python phone_ir_sender.py --send 0 # 0. sinyali gönder
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Sinyal veritabanı dosyası
DB_FILE = Path.home() / ".ir_signals.json"

# Bilinen IR protokolleri ve frekansları
PROTOCOLS = {
    "NEC":      {"freq": 38000, "header": [9000, 4500]},
    "SAMSUNG":  {"freq": 38000, "header": [4500, 4500]},
    "SONY":     {"freq": 40000, "header": [2400, 600]},
    "RC5":      {"freq": 36000, "header": [889, 889]},
    "RC6":      {"freq": 36000, "header": [2666, 889]},
    "LG":       {"freq": 38000, "header": [8000, 4000]},
}


def load_signals():
    """Kayıtlı sinyalleri yükle."""
    if DB_FILE.exists():
        with open(DB_FILE) as f:
            return json.load(f)
    return {"signals": []}


def save_signals(db):
    """Sinyalleri kaydet."""
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)


def add_signal(name, protocol, address, command, raw_data=None):
    """Yeni sinyal ekle."""
    db = load_signals()
    signal = {
        "name": name,
        "protocol": protocol,
        "address": address,
        "command": command,
        "raw_data": raw_data,
        "frequency": PROTOCOLS.get(protocol, {}).get("freq", 38000)
    }
    db["signals"].append(signal)
    save_signals(db)
    print(f"[+] Sinyal kaydedildi: {name}")


def list_signals():
    """Tüm kayıtlı sinyalleri listele."""
    db = load_signals()
    if not db["signals"]:
        print("[i] Henüz kayıtlı sinyal yok")
        return

    print("\n╔════╦══════════════════╦══════════╦══════════╦══════════╗")
    print("║ #  ║ İsim             ║ Protokol ║ Adres    ║ Komut    ║")
    print("╠════╬══════════════════╬══════════╬══════════╬══════════╣")
    for i, sig in enumerate(db["signals"]):
        name = sig["name"][:16].ljust(16)
        proto = sig["protocol"][:8].ljust(8)
        addr = sig["address"].ljust(8)
        cmd = sig["command"].ljust(8)
        print(f"║ {i:2d} ║ {name} ║ {proto} ║ {addr} ║ {cmd} ║")
    print("╚════╩══════════════════╩══════════╩══════════╩══════════╝")


def send_ir_termux(frequency, pattern):
    """
    Termux API ile IR sinyali gönder.
    Huawei P40'ın IR blaster'ını kullanır.
    """
    try:
        # Pattern'i string'e çevir
        pattern_str = ",".join(str(p) for p in pattern)

        # termux-infrared-transmit kullan
        result = subprocess.run(
            ["termux-infrared-transmit", "-f", str(frequency), pattern_str],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode == 0:
            print("[+] IR sinyali gönderildi!")
            return True
        else:
            print(f"[!] Hata: {result.stderr}")
            return False
    except FileNotFoundError:
        print("[!] termux-api bulunamadı. Kurulum:")
        print("    pkg install termux-api")
        print("    (Ayrıca Termux:API uygulamasını da yükle)")
        return False
    except subprocess.TimeoutExpired:
        print("[!] Zaman aşımı")
        return False


def nec_encode(address, command):
    """NEC protokolünü raw timing pattern'e çevir."""
    pattern = []

    # Header
    pattern.extend([9000, 4500])

    # Address (8 bit) + Address inverse (8 bit)
    addr = int(address, 16) if isinstance(address, str) else address
    cmd = int(command, 16) if isinstance(command, str) else command

    # Veriyi encode et: address, ~address, command, ~command
    data = (addr & 0xFF) | ((~addr & 0xFF) << 8) | ((cmd & 0xFF) << 16) | ((~cmd & 0xFF) << 24)

    for i in range(32):
        pattern.append(562)  # mark
        if data & (1 << i):
            pattern.append(1687)  # space (1)
        else:
            pattern.append(562)  # space (0)

    # Stop bit
    pattern.append(562)

    return pattern


def samsung_encode(address, command):
    """Samsung protokolünü raw timing pattern'e çevir."""
    pattern = []
    pattern.extend([4500, 4500])

    addr = int(address, 16) if isinstance(address, str) else address
    cmd = int(command, 16) if isinstance(command, str) else command

    # Samsung: address(16) + command(16)
    data = (addr & 0xFFFF) | ((cmd & 0xFFFF) << 16)

    for i in range(32):
        pattern.append(560)
        if data & (1 << i):
            pattern.append(1690)
        else:
            pattern.append(560)

    pattern.append(560)
    return pattern


def send_signal(index):
    """Kayıtlı sinyali gönder."""
    db = load_signals()

    if index >= len(db["signals"]):
        print(f"[!] Sinyal #{index} bulunamadı")
        return

    sig = db["signals"][index]
    print(f"[>] Gönderiliyor: {sig['name']} ({sig['protocol']})")

    freq = sig["frequency"]

    # Raw data varsa direkt gönder
    if sig.get("raw_data"):
        pattern = [int(x) for x in sig["raw_data"].split()]
        send_ir_termux(freq, pattern)
        return

    # Protokole göre encode et
    if sig["protocol"] == "NEC":
        pattern = nec_encode(sig["address"], sig["command"])
    elif sig["protocol"] == "SAMSUNG":
        pattern = samsung_encode(sig["address"], sig["command"])
    else:
        print(f"[!] {sig['protocol']} protokolü için encoder yok")
        print("[i] Raw data gerekli")
        return

    send_ir_termux(freq, pattern)


def parse_arduino_output(line):
    """Arduino seri çıktısını parse et ve sinyal olarak kaydet."""
    # Arduino'dan gelen format:
    # [+] SINYAL YAKALANDI #0
    #     Protokol : NEC
    #     Adres    : 0x04
    #     Komut    : 0x08
    pass  # Interaktif modda kullanılır


def interactive_mode():
    """Interaktif menü."""
    print("\n╔══════════════════════════════════════╗")
    print("║   TELEFON IR GÖNDERİCİ v1.0         ║")
    print("║   Huawei P40 IR Blaster              ║")
    print("╠══════════════════════════════════════╣")
    print("║ 1 - Kayıtlı sinyalleri listele       ║")
    print("║ 2 - Yeni sinyal ekle (manuel)         ║")
    print("║ 3 - Sinyal gönder                     ║")
    print("║ 4 - Hızlı TV aç/kapa (NEC)           ║")
    print("║ 5 - Hızlı TV aç/kapa (Samsung)       ║")
    print("║ 0 - Çıkış                             ║")
    print("╚══════════════════════════════════════╝")

    while True:
        try:
            choice = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[*] Çıkış")
            break

        if choice == "1":
            list_signals()

        elif choice == "2":
            name = input("  Sinyal adı: ").strip()
            proto = input("  Protokol (NEC/SAMSUNG/SONY/RC5): ").strip().upper()
            addr = input("  Adres (hex, ör: 0x04): ").strip()
            cmd = input("  Komut (hex, ör: 0x08): ").strip()
            raw = input("  Raw data (boş bırakabilirsin): ").strip() or None
            add_signal(name, proto, addr, cmd, raw)

        elif choice == "3":
            list_signals()
            idx = int(input("  Sinyal #: ").strip())
            send_signal(idx)

        elif choice == "4":
            # Genel NEC power toggle
            print("[>] NEC Power Toggle gönderiliyor...")
            pattern = nec_encode(0x04, 0x08)
            send_ir_termux(38000, pattern)

        elif choice == "5":
            # Samsung power toggle
            print("[>] Samsung Power Toggle gönderiliyor...")
            pattern = samsung_encode(0x0707, 0x0202)
            send_ir_termux(38000, pattern)

        elif choice == "0":
            print("[*] Çıkış")
            break

        else:
            print("[!] Geçersiz seçim")


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_signals()
    elif "--send" in sys.argv:
        idx = int(sys.argv[sys.argv.index("--send") + 1])
        send_signal(idx)
    else:
        interactive_mode()
