# BIST EMA Kırılım Tarayıcısı

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-green.svg)](LICENSE)
[![Durum: Aktif](https://img.shields.io/badge/durum-aktif-success.svg)]()

Borsa İstanbul (BIST) hisselerini her seans sonu tarayan, EMA-20 / EMA-50 kırılım sinyallerini bulan bir araç. Endeks listesini KAP'tan (yedek olarak Midas), fiyat verilerini Yahoo Finance'tan alır. Hem o günkü sinyalleri hem de zaman içinde sinyallerin sonrasında ne olduğunu otomatik olarak CSV'lere kaydeder; böylece sinyal kalitesini somut veriyle değerlendirebilirsin.

**[English README →](README.md)**

---

## Ne yapar

BIST kapanışından sonra `bist_ema_scanner.py`'yi çalıştırırsın. Seçtiğin endeksteki (varsayılan XU100, alternatif XU500) her hisse için Yahoo Finance'tan son 6 ayın günlük mumlarını çeker, EMA-20 ve EMA-50'yi hesaplar, ve bugünkü kapanışı iki kırılım örüntüsünden birine uyan hisseleri ekrana basar. Bulunan sinyaller bir CSV'ye eklenir; geçmişteki her sinyalin sonraki 1, 3, 5 ve 10 günlük getirisi de yeni günler geçtikçe otomatik olarak doldurulur.

## Sinyal tanımı

Bir hisse şu koşullar sağlandığında listede çıkar: **bugünün kapanışı hem EMA-20 hem EMA-50'nin üstünde**, VE aşağıdakilerden en az biri:

- **BRK — Kırılım (Breakout).** Dünkü kapanış üstteki EMA'nın altındaymış. Klasik kırılımları ve gap-up'la başlayan kırılımları kapsar.
- **GDN — Aşağı boşluklu açılışta toparlanma (Gap-Down Recovery).** Bugünün açılışı üstteki EMA'nın altındaymış, ama kapanış iki EMA'nın da üstünde tamamlanmış. Yukarı trend içinde olan bir hissenin haberle aşağı açıp gün içinde toparlanma vakasını yakalar.

EMA-20 ve EMA-50'nin hangisinin üstte olduğu önemli değil — açılış/dünkü kapanış testi için sadece üstteki EMA'ya bakılır, kapanış ise iki EMA'nın da üstünde olmak zorundadır.

### Bu sinyal niye?

Fiyatın hem iki EMA'nın üstünde olması, hem de yakın geçmişte birinin altında olması — gün sonu grafik bakan bir alıcının gözünden bakınca — trend çizgisini yeni geri almış bir hisse demek. İki tane pratik kısıtlama var, bilmekte fayda var:

- **Whipsaw (yalancı kırılım) riski.** Yatay piyasalarda kırılımlar ertesi gün geri döner. Hacim teyidi sütunu (`VOL×`, bugün vs. son 20 günün ortalaması) zayıf sinyalleri ayırt etmeye yardım eder.
- **Geç giriş riski.** EMA'lar gecikmeli göstergelerdir. Sinyal tetiklendiğinde hareketin önemli kısmı çoktan yaşanmış olabilir. Bu araç bir **ön süzgeç**, alım sinyali değil.

Bu araç al/sat tavsiyesi vermez. [Yasal Uyarı](#yasal-uyarı) bölümüne bak.

## Örnek çıktı

```
===============================================================================================
XU500 EMA Breakout Scan  |  Session: 2026-04-27  |  Scanned at: 2026-04-27 18:35
Close above both EMAs, with either yesterday's close or today's open below the upper EMA
Marking signals with BREAK% >= 0.5% (all signals are still logged)
===============================================================================================
59 match(es):  [ BRK=breakout  GDN=gap-down recovery  * = vol >= 1.5x  ✓ = BREAK% >= 0.5%  ★ = BREAK% >= 2.0% AND VOL >= 2.0x ]

   TICKER     DATE         TYPE   Y-CLOSE   Y-EMA20   Y-EMA50     OPEN    CLOSE   T-EMA20   T-EMA50   BREAK%    VOL×
--------------------------------------------------------------------------------------------------------------------------
★ EUPWR.IS   2026-04-27   BRK      40.58     40.65     39.16    41.20    44.62     41.02     39.37   +8.76%   2.50*
★ TATGD.IS   2026-04-27   BRK      16.55     16.70     16.35    16.55    17.57     16.79     16.40   +4.66%   2.97*
✓ OYYAT.IS   2026-04-27   BRK      56.10     56.30     55.93    56.15    58.80     56.53     56.04   +4.01%   0.44 
✓ KFEIN.IS   2026-04-27   BRK       8.76      8.63      8.77     8.79     9.05      8.67      8.78   +3.12%   1.59*
✓ ADGYO.IS   2026-04-27   BRK      58.50     58.62     57.66    59.00    60.60     58.81     57.77   +3.05%   0.66 
...
  TUPRS.IS   2026-04-27   BRK     253.00    254.90    241.18   260.25   255.00    254.91    241.72   +0.04%   0.65 
Logged 59 signal(s) to signals_log_xu500.csv
```

İşaretler:

- **`★`** — Güçlü kırılım: BREAK% ≥ %2 VE hacim ≥ 20 günlük ortalamanın 2 katı. Ampirik olarak en yüksek güvenilirlik kategorisi.
- **`✓`** — Marjinal eşiğin üstünde (BREAK% ≥ `--min-break`, varsayılan %0.5). Varsayılan olarak açık; `-m 0` ile devre dışı bırakılabilir.
- (işaret yok) — Marjinal sinyal. Log'a yazılır ama görsel olarak vurgulanmaz; tarihsel olarak bu kategorinin başarı oranı düşük.

Tüm sinyaller — marjinaller dahil — log dosyasına yazılır. İşaretler sadece terminaldeki gösterimi etkiler, böylece eşik üzerinde deneme yapabilirsin (veri kaybı olmadan).

Sütunlar:

| Sütun        | Anlamı                                                                       |
|--------------|------------------------------------------------------------------------------|
| `TYPE`       | `BRK` = kırılım, `GDN` = aşağı boşluklu açılıştan toparlanma                  |
| `Y-CLOSE`    | Dünkü kapanış                                                                |
| `Y-EMA20/50` | Dünkü EMA değerleri                                                          |
| `OPEN`       | Bugünün açılışı                                                              |
| `CLOSE`      | Bugünün kapanışı                                                             |
| `T-EMA20/50` | Bugünün EMA değerleri                                                        |
| `BREAK%`     | Kapanışın üstteki EMA'nın yüzde kaç üstünde olduğu — büyükse daha güçlü kırılım |
| `VOL×`       | Bugünün hacmi / son 20 günün ortalaması. `*` işareti ≥ 1.5× anlamına gelir   |

Satırlar `BREAK%`'ye göre büyükten küçüğe sıralanır; en net kırılımlar tepededir.

## Kurulum

Python 3.10+ gerekir.

```bash
git clone https://github.com/bkadirbeyoglu/bist-ema-scanner.git
cd bist-ema-scanner
pip install -r requirements.txt
```

`requirements.txt`:

```
yfinance
pandas
requests
```

## Kullanım

İki adımlı bir akış: hisse listesini ara sıra yenile, sonra tarayıcıyı her gün seans kapanışından sonra çalıştır.

### 1. Hisse listesini yenile

Endeksler üç ayda bir yeniden dengelenir. Gerektiğinde tekrar çalıştır:

```bash
python update_index.py                    # XU100 → xu100.csv  (varsayılan)
python update_index.py -i xu500           # XU500 → xu500.csv
python update_index.py -i xu500 -s midas  # KAP çalışmazsa Midas'tan al
```

### 2. Tarayıcıyı çalıştır

BIST 18:00'de kapanır; Yahoo'nun günlük barı 15-30 dk içinde oturur. Tarayıcıyı 18:30 civarında çalıştır:

```bash
python bist_ema_scanner.py                    # XU100 (varsayılan)
python bist_ema_scanner.py -i xu500           # XU500
python bist_ema_scanner.py -d 2026-04-17      # belirli bir geçmiş seansı tara
python bist_ema_scanner.py -m 1.0             # ✓ eşiğini %1'e yükselt
python bist_ema_scanner.py -m 0               # marjinal sinyal vurgusunu kapat
python bist_ema_scanner.py --no-log           # log dosyalarına yazma
```

### 3. Tek bir hisseyi incele

Belirli bir hissenin niye sinyal verdiğini ya da niye vermediğini anlamak için:

```bash
python debug_ticker.py HALKB
```

## Çıktı dosyaları

Her endeksin kendi log dosya çifti vardır; sonuçlar asla karışmaz:

```
xu100.csv                  ← hisse listesi (update_index.py oluşturur)
xu500.csv

signals_log_xu100.csv      ← şimdiye kadarki tüm sinyaller
signals_log_xu500.csv

outcomes_xu100.csv         ← her sinyalin 1, 3, 5, 10 gün sonra ne olduğu
outcomes_xu500.csv
```

### `signals_log_xu*.csv`

Sadece eklenen geçmiş kayıt dosyası. Sütunlar: `scan_date, signal_date, ticker, trigger, y_close, y_ema20, y_ema50, open, close, t_ema20, t_ema50, break_pct, vol_ratio`.

`(scan_date, signal_date, ticker)` üçlüsüne göre mükerrer kayıt korumalı — aynı gün tarayıcıyı kaç kez çalıştırırsan çalıştır sorun olmaz.

### `outcomes_xu*.csv`

Kendi kendini güncelleyen dosya. Yeni sinyaller boş outcome hücreleriyle eklenir. Sonraki çalıştırmalarda tarayıcı şunları doldurur:

- `d{1,3,5,10}_open` / `d{1,3,5,10}_close` / `d{1,3,5,10}_pct` — her takip barındaki açılış ve kapanış, ayrıca `signal_close`'a göre kapanış-kapanış yüzde getirisi. `d{n}_open` kolonları, sinyal-günü kapanışı (alıp satılamaz) yerine ertesi gün açılışında alarak elde edebileceğin **gerçek getiriyi** ölçmeye yarar.
- `max_5d_close` / `max_5d_pct` — sinyalden sonraki ilk 5 seansta görülen en yüksek kapanış.
- `xu100_close` / `xu100_d1_close` — sinyal günü ve d1 günü BIST 100 endeksi kapanışı. **Piyasaya göre rölatif** getiriyi (sinyal d1 - endeks d1) ek bir veri çekme yapmadan hesaplamana izin verir.

Birkaç hafta sonra bu dosya analiz için altın değerinde olur: Excel'de aç, `trigger`'a göre, `vol_ratio` aralıklarına göre, `break_pct` quintile'larına göre, gap büyüklüğüne göre (`d1_open - signal_close`) ya da piyasa-rölatif performansa göre pivot çek ve hangi koşulların gerçekten pozitif getiri öngördüğünü gör.

## Proje yapısı

```
bist-ema-scanner/
├── bist_ema_scanner.py         # Ana tarayıcı
├── update_index.py         # Hisse listesi yenileyici (KAP + Midas yedek)
├── debug_ticker.py         # Tek hisse teşhis aracı
├── xu100.csv               # Hisse listeleri (oluşturulur)
├── xu500.csv
├── signals_log_xu*.csv     # Sinyal geçmişi (oluşturulur)
├── outcomes_xu*.csv        # Sonuç takibi (oluşturulur)
├── requirements.txt
├── LICENSE
├── README.md
└── README.tr.md
```

## Veri kaynakları

- **Hisse listeleri:** [KAP (Kamuyu Aydınlatma Platformu)](https://kap.org.tr/tr/Endeksler) — birincil. [Midas](https://www.getmidas.com/canli-borsa/) — yedek.
- **Fiyat geçmişi:** [Yahoo Finance](https://finance.yahoo.com/), `yfinance` kütüphanesi üzerinden, `auto_adjust=True` ile — yani EMA'lar temettü ve bedelsizlerden arındırılmış kapanışlar üzerinden hesaplanır.

## Sınırlamalar ve bilinen sorunlar

- **Yahoo veri gecikmesi:** BIST kapanışından ~15-30 dk sonra. Tarayıcıyı 18:30'dan önce çalıştırma, yoksa bugünün barı eksik gelir.
- **Düzeltilmiş fiyatlar:** Yahoo'nun düzeltmesi her zaman BIST hisselerinde mükemmel olmuyor — özellikle bedelsiz sermaye artırımı yapanlarda. Bir sayı tuhaf görünüyorsa aracı kurumunun grafiğinden kontrol et.
- **Borsa dışı kalan hisseler:** BIST'ten çıkarılan bir hisse için yfinance "possibly delisted" uyarısı verir. Üç aylık dengelemeden sonra `update_index.py`'yi tekrar çalıştırarak listeyi tazele.
- **Al/sat tavsiyesi değildir.** Bu sinyal tek başına yaklaşık yazı-tura isabet oranındadır (crossover stratejilerinin tipik özelliği). Asıl avantaj pozisyon büyüklüğü, zarar-kes (stop-loss) ve piyasa rejimi filtreleriyle birleştiğinde gelir — bu araç bunların hiçbirini içermez.

## Katkı

Issue ve pull request'ler memnuniyetle kabul edilir. Bir strateji değişikliği öneriyorsan (ör. yeni bir trigger tipi), lütfen geçmiş `outcomes_xu*.csv` verisi üzerinden nasıl performans gösterdiğine dair kısa bir analiz ekle.

## Yasal uyarı

Bu yazılım yalnızca eğitim ve araştırma amaçlıdır. **Yatırım tavsiyesi değildir.** Yazar lisanslı bir yatırım danışmanı değildir. Borsa işlemleri zarar etme riski içerir; karar vermeden önce kendi araştırmanı yap ve yetkin bir profesyonele danış. Geçmiş performans — bu aracın ürettiği analizler dahil — gelecekteki sonuçları garanti etmez.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
