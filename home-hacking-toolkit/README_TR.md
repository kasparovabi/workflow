# Home Hacking Toolkit

Eski telefonlar (Huawei P40, Samsung A71) ve Arduino ile evdeki
elektronik cihazları keşfetmek, analiz etmek ve kontrol etmek için araçlar.

## Araçlar

### 1. IR Sinyal Yakalayıcı (`ir-interceptor/`)
Arduino + IR alıcı ile herhangi bir kumandanın sinyalini yakala ve tekrarla.
- `ir_capture.ino` — Arduino sketch'i (yakalama, tekrarlama, brute-force)
- `phone_ir_sender.py` — Huawei P40 IR blaster ile gönderme (Termux)
- `DEVRE.txt` — Bağlantı şeması

### 2. WiFi Ağ Tarayıcı (`wifi-scanner/`)
Evdeki tüm WiFi cihazlarını bul, üreticisini tanımla, portlarını tara.
- `network_scanner.py` — ARP tarama, port tarama, cihaz tanıma

### 3. Bluetooth Avcısı (`bluetooth-scanner/`)
Etraftaki tüm BLE cihazları keşfet, mesafe hesapla, cihaz tipini tahmin et.
- `ble_scanner.py` — BLE tarama, izleme, tek cihaz takibi

## Gereksinimler

**Telefon (Termux):**
```
pkg install python
pip install bleak
```

**Arduino:**
- IRremote kütüphanesi (Library Manager'dan yükle)

## Hızlı Başlangıç

```bash
# WiFi'daki cihazları tara
python wifi-scanner/network_scanner.py --quick

# Bluetooth cihazları bul
python bluetooth-scanner/ble_scanner.py

# Ağı sürekli izle (yeni cihaz bildirimi)
python wifi-scanner/network_scanner.py --monitor
```
