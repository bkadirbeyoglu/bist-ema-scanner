# BIST EMA Kırılım Tarayıcısı

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-green.svg)](LICENSE)
[![Durum: Aktif](https://img.shields.io/badge/durum-aktif-success.svg)]()

Borsa İstanbul (BIST) hisselerini her seans sonu tarayan, EMA-20 / EMA-50 kırılım sinyallerini bulan bir araç. Endeks listesini KAP'tan (yedek olarak Midas), fiyat verilerini Yahoo Finance'tan alır. Hem o günkü sinyalleri hem de zaman içinde sinyallerin sonrasında ne olduğunu otomatik olarak CSV'lere kaydeder; böylece sinyal kalitesini somut veriyle değerlendirebilirsin.

**[English README →](README.md)**

---

## Ne yapar

BIST kapanışından sonra `bist_ema_scanner.py`'yi çalıştırırsın. Seçtiğin endeksteki (varsayılan XU100, alternatif XU500) her hisse için Yahoo Finance'tan son 6 ayın günlük mumlarını çeker, EMA-20 ve EMA-50'yi hesaplar, ve bugünkü kapanışı kırılım örüntüsüne uyan hisseleri ekrana basar. Bulunan sinyaller bir CSV'ye eklenir; geçmişteki her sinyalin sonraki 1, 3, 5 ve 10 günlük getirisi de yeni günler geçtikçe otomatik olarak doldurulur.

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
XU100 EMA Breakout Scan  |  Session: 2026-04-17  |  Scanned at: 2026-04-17 19:00
Close above both EMAs, with either yesterday's close or today's open below the upper EMA
===============================================================================================
14 match(es):  [ BRK=breakout  GDN=gap-down recovery  * = vol >= 1.5x ]

TICKER     DATE         TYPE   Y-CLOSE   Y-EMA20   Y-EMA50     OPEN    CLOSE   T-EMA20   T-EMA50   BREAK%    VOL×
------------------------------------------------------------------------------------------------------------------------
ZOREN.IS   2026-04-17   BRK       3.00      2.92      3.02     3.00     3.21      2.95      3.02   +6.15%   2.01*
BALSU.IS   2026-04-17   BRK      15.02     14.69     15.09    15.03    15.89     14.81     15.12   +5.10%   2.64*
EKGYO.IS   2026-04-17   BRK      20.96     20.63     21.24    20.98    22.34     20.80     21.28   +4.98%   1.69*
PGSUS.IS   2026-04-17   BRK     186.00    183.16    187.44   186.50   196.90    184.47    187.81   +4.84%   2.27*
VAKBN.IS   2026-04-17   BRK      33.82     33.29     33.87    33.74    35.40     33.49     33.93   +4.34%   2.78*
HALKB.IS   2026-04-17   BRK      39.42     39.12     40.57    39.48    41.14     39.31     40.60   +1.34%   1.88*
TAVHL.IS   2026-04-17   BRK     311.75    319.09    315.83   312.75   320.00    319.17    316.00   +0.26%   3.29*
...
Logged 14 signal(s) to signals_log_xu100.csv
```

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

Kendi kendini güncelleyen dosya. Yeni sinyaller boş outcome hücreleriyle eklenir. Sonraki çalıştırmalarda tarayıcı `d1_close`, `d1_pct`, `d3_close`, `d3_pct`, … `d10_close`, `d10_pct` ve ayrıca `max_5d_close` / `max_5d_pct` (sinyalden sonraki ilk 5 seansta görülen en yüksek kapanış) sütunlarını kendiliğinden doldurur.

Birkaç hafta sonra bu dosya analiz için altın değerinde olur: Excel'de aç, `trigger`'a göre, `vol_ratio` aralıklarına göre, `break_pct` quintile'larına göre pivot çek ve hangi koşulların gerçekten pozitif getiri öngördüğünü gör.

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