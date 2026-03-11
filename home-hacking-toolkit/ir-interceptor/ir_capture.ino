/*
 * IR Sinyal Yakalayıcı & Tekrarlayıcı
 * =====================================
 * Evdeki herhangi bir kumandanın IR sinyalini yakalar,
 * protokolünü çözer ve seri port üzerinden raporlar.
 * Yakalanan sinyali IR LED ile tekrar gönderebilir.
 *
 * Devre:
 *   - IR Alıcı (TSOP1738/VS1838B) -> Pin 2
 *   - IR LED (kumandadan söktüğün) -> Pin 3 (220 ohm direnç ile)
 *   - Buton (tekrar gönder) -> Pin 4 (dahili pull-up)
 *   - Durum LED'i -> Pin 13 (dahili LED)
 *
 * Gerekli kütüphane: IRremote (Arduino Library Manager'dan yükle)
 */

#include <IRremote.h>

// --- Pin Tanımları ---
#define IR_RECEIVE_PIN  2
#define IR_SEND_PIN     3
#define REPLAY_BUTTON   4
#define STATUS_LED      13

// --- Yakalanan sinyal deposu (son 10 sinyal) ---
#define MAX_SIGNALS     10

struct CapturedSignal {
  decode_type_t protocol;
  uint32_t address;
  uint32_t command;
  uint16_t rawData[200];
  uint16_t rawLen;
  bool valid;
};

CapturedSignal signals[MAX_SIGNALS];
int signalCount = 0;
int currentIndex = 0;

// --- Mod ---
enum Mode { CAPTURE, REPLAY, BRUTEFORCE };
Mode currentMode = CAPTURE;

void setup() {
  Serial.begin(115200);
  while (!Serial); // Leonardo/Micro için bekle

  pinMode(REPLAY_BUTTON, INPUT_PULLUP);
  pinMode(STATUS_LED, OUTPUT);

  IrReceiver.begin(IR_RECEIVE_PIN);

  // Başlangıç bilgisi
  Serial.println(F(""));
  Serial.println(F("╔══════════════════════════════════════╗"));
  Serial.println(F("║   IR SİNYAL YAKALAYICI v1.0         ║"));
  Serial.println(F("║   Home Hacking Toolkit               ║"));
  Serial.println(F("╠══════════════════════════════════════╣"));
  Serial.println(F("║ Komutlar:                            ║"));
  Serial.println(F("║   c - Yakalama modu (varsayilan)     ║"));
  Serial.println(F("║   r - Tekrarlama modu                ║"));
  Serial.println(F("║   b - Brute-force modu               ║"));
  Serial.println(F("║   l - Yakalanan sinyalleri listele   ║"));
  Serial.println(F("║   s<N> - N. sinyali gonder           ║"));
  Serial.println(F("║   d - Tum sinyalleri sil             ║"));
  Serial.println(F("║   ? - Yardim                         ║"));
  Serial.println(F("╚══════════════════════════════════════╝"));
  Serial.println(F(""));
  Serial.println(F("[*] IR Alici baslatildi, pin: 2"));
  Serial.println(F("[*] Kumandayi aliciya dogrult ve bir tusa bas..."));
  Serial.println(F(""));

  // Durum LED'i - hazır
  blinkLed(3, 100);
}

void loop() {
  // Seri port komutlarını kontrol et
  handleSerialCommands();

  // Fiziksel buton - son sinyali tekrar gönder
  if (digitalRead(REPLAY_BUTTON) == LOW) {
    delay(50); // debounce
    if (digitalRead(REPLAY_BUTTON) == LOW) {
      replayLastSignal();
      while (digitalRead(REPLAY_BUTTON) == LOW); // bırakılana kadar bekle
    }
  }

  // Modlara göre işlem
  switch (currentMode) {
    case CAPTURE:
      captureMode();
      break;
    case REPLAY:
      // Replay modunda seri komut bekler
      break;
    case BRUTEFORCE:
      // Brute force seri komutla başlatılır
      break;
  }
}

// ============================================
// YAKALAMA MODU
// ============================================
void captureMode() {
  if (IrReceiver.decode()) {
    digitalWrite(STATUS_LED, HIGH);

    // Sinyali kaydet
    CapturedSignal* sig = &signals[currentIndex];
    sig->protocol = IrReceiver.decodedIRData.protocol;
    sig->address = IrReceiver.decodedIRData.address;
    sig->command = IrReceiver.decodedIRData.command;
    sig->valid = true;

    // Raw veriyi kaydet
    sig->rawLen = min((int)IrReceiver.decodedIRData.rawDataPtr->rawlen, 200);
    for (uint16_t i = 0; i < sig->rawLen; i++) {
      sig->rawData[i] = IrReceiver.decodedIRData.rawDataPtr->rawbuf[i] * MICROS_PER_TICK;
    }

    // Seri porta raporla
    Serial.print(F("\n[+] SINYAL YAKALANDI #"));
    Serial.println(signalCount);
    Serial.println(F("    ─────────────────────────"));

    // Protokol bilgisi
    Serial.print(F("    Protokol : "));
    Serial.println(getProtocolString(sig->protocol));

    Serial.print(F("    Adres    : 0x"));
    Serial.println(sig->address, HEX);

    Serial.print(F("    Komut    : 0x"));
    Serial.println(sig->command, HEX);

    Serial.print(F("    Bit      : "));
    Serial.println(IrReceiver.decodedIRData.numberOfBits);

    // Raw timing bilgisi
    Serial.print(F("    Raw uzun.: "));
    Serial.print(sig->rawLen);
    Serial.println(F(" pulse"));

    // Raw veriyi hex dump olarak göster
    Serial.print(F("    Raw data : "));
    for (uint16_t i = 1; i < min((uint16_t)20, sig->rawLen); i++) {
      Serial.print(sig->rawData[i]);
      Serial.print(F(" "));
    }
    if (sig->rawLen > 20) Serial.print(F("..."));
    Serial.println();

    // Bilinen cihaz tahmini
    guessDevice(sig);

    Serial.println(F("    ─────────────────────────"));
    Serial.print(F("    [i] 's"));
    Serial.print(signalCount);
    Serial.println(F("' yazarak tekrar gonderebilirsin"));

    // İndeksleri güncelle
    currentIndex = (currentIndex + 1) % MAX_SIGNALS;
    if (signalCount < MAX_SIGNALS) signalCount++;

    digitalWrite(STATUS_LED, LOW);
    IrReceiver.resume();
  }
}

// ============================================
// SİNYAL TEKRARLAMA
// ============================================
void replaySignal(int index) {
  if (index < 0 || index >= signalCount || !signals[index].valid) {
    Serial.println(F("[!] Gecersiz sinyal indeksi"));
    return;
  }

  CapturedSignal* sig = &signals[index];

  Serial.print(F("[>] Sinyal #"));
  Serial.print(index);
  Serial.print(F(" gonderiliyor ("));
  Serial.print(getProtocolString(sig->protocol));
  Serial.println(F(")..."));

  // LED göstergesi
  digitalWrite(STATUS_LED, HIGH);

  // Bilinen protokolse protokol bazlı gönder
  if (sig->protocol != UNKNOWN) {
    IrSender.begin(IR_SEND_PIN);

    switch (sig->protocol) {
      case NEC:
        IrSender.sendNEC(sig->address, sig->command, 2);
        break;
      case SAMSUNG:
        IrSender.sendSamsung(sig->address, sig->command, 2);
        break;
      case SONY:
        IrSender.sendSony(sig->address, sig->command, 2);
        break;
      case RC5:
        IrSender.sendRC5(sig->address, sig->command, 2);
        break;
      case RC6:
        IrSender.sendRC6(sig->address, sig->command, 2);
        break;
      default:
        // Diğer protokoller için raw gönder
        IrSender.sendRaw(sig->rawData + 1, sig->rawLen - 1, 38);
        break;
    }
  } else {
    // Bilinmeyen protokol - raw olarak gönder
    IrSender.begin(IR_SEND_PIN);
    IrSender.sendRaw(sig->rawData + 1, sig->rawLen - 1, 38);
  }

  Serial.println(F("[+] Gonderildi!"));
  digitalWrite(STATUS_LED, LOW);

  // Tekrar yakalamayı başlat
  IrReceiver.start();
}

void replayLastSignal() {
  if (signalCount == 0) {
    Serial.println(F("[!] Henuz yakalanan sinyal yok"));
    return;
  }
  int lastIdx = (currentIndex - 1 + MAX_SIGNALS) % MAX_SIGNALS;
  replaySignal(lastIdx);
}

// ============================================
// BRUTE FORCE (egitim amacli)
// ============================================
void bruteForceNEC(uint16_t targetAddress) {
  Serial.println(F("[*] NEC Brute Force baslatiliyor..."));
  Serial.print(F("[*] Hedef adres: 0x"));
  Serial.println(targetAddress, HEX);
  Serial.println(F("[*] Durdurmak icin 'x' gonder"));

  IrSender.begin(IR_SEND_PIN);

  for (uint16_t cmd = 0; cmd <= 0xFF; cmd++) {
    // Durdurma kontrolü
    if (Serial.available() && Serial.read() == 'x') {
      Serial.println(F("\n[!] Brute force durduruldu"));
      IrReceiver.start();
      return;
    }

    IrSender.sendNEC(targetAddress, cmd, 2);

    Serial.print(F("\r[>] Komut: 0x"));
    if (cmd < 0x10) Serial.print(F("0"));
    Serial.print(cmd, HEX);
    Serial.print(F(" ("));
    Serial.print(cmd);
    Serial.print(F("/255)"));

    delay(100); // Cihazın işlemesi için bekle
  }

  Serial.println(F("\n[+] Brute force tamamlandi (256 komut denendi)"));
  IrReceiver.start();
}

// ============================================
// SERİ PORT KOMUTLARI
// ============================================
void handleSerialCommands() {
  if (!Serial.available()) return;

  char cmd = Serial.read();

  switch (cmd) {
    case 'c':
      currentMode = CAPTURE;
      Serial.println(F("\n[*] YAKALAMA moduna gecildi"));
      Serial.println(F("[*] Kumandayi aliciya dogrult..."));
      IrReceiver.start();
      break;

    case 'r':
      currentMode = REPLAY;
      Serial.println(F("\n[*] TEKRARLAMA moduna gecildi"));
      Serial.println(F("[*] 's<N>' ile sinyal gonder (orn: s0, s1, s2)"));
      break;

    case 'b': {
      currentMode = BRUTEFORCE;
      Serial.println(F("\n[*] BRUTE FORCE modu"));

      // Eğer yakalanan sinyal varsa onun adresini kullan
      if (signalCount > 0) {
        int lastIdx = (currentIndex - 1 + MAX_SIGNALS) % MAX_SIGNALS;
        Serial.print(F("[*] Son yakalanan adres kullanilacak: 0x"));
        Serial.println(signals[lastIdx].address, HEX);
        Serial.println(F("[*] 'y' ile onayla, baska adres icin hex gir"));

        // Basit onay bekle
        while (!Serial.available());
        char confirm = Serial.read();
        if (confirm == 'y') {
          bruteForceNEC(signals[lastIdx].address);
        }
      } else {
        Serial.println(F("[!] Once bir sinyal yakala (adres gerekli)"));
        currentMode = CAPTURE;
      }
      break;
    }

    case 'l':
      listSignals();
      break;

    case 's': {
      // s0, s1, s2... şeklinde sinyal gönder
      while (!Serial.available()); // sayıyı bekle
      int idx = Serial.parseInt();
      replaySignal(idx);
      break;
    }

    case 'd':
      signalCount = 0;
      currentIndex = 0;
      for (int i = 0; i < MAX_SIGNALS; i++) signals[i].valid = false;
      Serial.println(F("[*] Tum sinyaller silindi"));
      break;

    case '?':
      printHelp();
      break;

    case '\n':
    case '\r':
      break; // Boş satırları yoksay

    default:
      Serial.print(F("[!] Bilinmeyen komut: "));
      Serial.println(cmd);
      break;
  }
}

// ============================================
// YARDIMCI FONKSİYONLAR
// ============================================
void listSignals() {
  if (signalCount == 0) {
    Serial.println(F("\n[i] Henuz yakalanan sinyal yok"));
    return;
  }

  Serial.println(F("\n┌────┬──────────┬──────────┬──────────┐"));
  Serial.println(F("│ #  │ Protokol │  Adres   │  Komut   │"));
  Serial.println(F("├────┼──────────┼──────────┼──────────┤"));

  for (int i = 0; i < signalCount; i++) {
    if (!signals[i].valid) continue;
    Serial.print(F("│ "));
    if (i < 10) Serial.print(F(" "));
    Serial.print(i);
    Serial.print(F(" │ "));
    printPadded(getProtocolString(signals[i].protocol), 8);
    Serial.print(F(" │ 0x"));
    printHexPadded(signals[i].address, 4);
    Serial.print(F("   │ 0x"));
    printHexPadded(signals[i].command, 4);
    Serial.println(F("   │"));
  }
  Serial.println(F("└────┴──────────┴──────────┴──────────┘"));
}

void guessDevice(CapturedSignal* sig) {
  Serial.print(F("    Cihaz    : "));
  // Bilinen adreslerle eşleştirme dene
  if (sig->protocol == NEC) {
    switch (sig->address) {
      case 0x04: Serial.println(F("Samsung TV (muhtemelen)")); return;
      case 0x07: Serial.println(F("Samsung TV")); return;
      case 0x02: Serial.println(F("Sony TV (muhtemelen)")); return;
      case 0x04FB: Serial.println(F("LG TV")); return;
      case 0xFF: Serial.println(F("LED serit kumanda")); return;
      case 0x00: Serial.println(F("Genel NEC cihazi")); return;
    }
  }
  if (sig->protocol == SAMSUNG) {
    Serial.println(F("Samsung cihazi")); return;
  }
  if (sig->protocol == SONY) {
    Serial.println(F("Sony cihazi")); return;
  }
  Serial.println(F("Bilinmeyen (yeni cihaz!)"));
}

const char* getProtocolString(decode_type_t protocol) {
  switch (protocol) {
    case NEC: return "NEC";
    case SAMSUNG: return "SAMSUNG";
    case SONY: return "SONY";
    case RC5: return "RC5";
    case RC6: return "RC6";
    case PANASONIC: return "PANASON";
    case JVC: return "JVC";
    case LG: return "LG";
    case SHARP: return "SHARP";
    case DENON: return "DENON";
    default: return "UNKNOWN";
  }
}

void printHexPadded(uint32_t val, int width) {
  int digits = 1;
  uint32_t tmp = val >> 4;
  while (tmp) { digits++; tmp >>= 4; }
  for (int i = 0; i < width - digits; i++) Serial.print('0');
  Serial.print(val, HEX);
}

void printPadded(const char* str, int width) {
  int len = strlen(str);
  Serial.print(str);
  for (int i = len; i < width; i++) Serial.print(' ');
}

void blinkLed(int times, int interval) {
  for (int i = 0; i < times; i++) {
    digitalWrite(STATUS_LED, HIGH);
    delay(interval);
    digitalWrite(STATUS_LED, LOW);
    delay(interval);
  }
}

void printHelp() {
  Serial.println(F("\n=== KOMUTLAR ==="));
  Serial.println(F("  c        - Yakalama modu"));
  Serial.println(F("  r        - Tekrarlama modu"));
  Serial.println(F("  b        - NEC brute-force"));
  Serial.println(F("  l        - Sinyalleri listele"));
  Serial.println(F("  s<N>     - N. sinyali gonder (orn: s0)"));
  Serial.println(F("  d        - Tum sinyalleri sil"));
  Serial.println(F("  ?        - Bu yardim"));
  Serial.println(F("\n=== DEVRE ==="));
  Serial.println(F("  IR Alici  -> Pin 2"));
  Serial.println(F("  IR LED    -> Pin 3 (220ohm direnc ile)"));
  Serial.println(F("  Buton     -> Pin 4 (son sinyali tekrarla)"));
  Serial.println(F("  LED       -> Pin 13 (durum)"));
}
