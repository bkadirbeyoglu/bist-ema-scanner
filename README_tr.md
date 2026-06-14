# BIST EMA Kırılım Tarayıcısı

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-green.svg)](LICENSE)
[![Durum: Aktif](https://img.shields.io/badge/durum-aktif-success.svg)]()

Borsa İstanbul (BIST) hisselerini her seans sonu tarayan, EMA-20 / EMA-50 kırılım sinyallerini bulan bir araç. Endeks listesini KAP'tan (yedek olarak Midas), fiyat verilerini Yahoo Finance'tan alır. Hem o günkü sinyalleri hem de zaman içinde sinyallerin sonrasında ne olduğunu otomatik olarak CSV'lere kaydeder; böylece sinyal kalitesini somut veriyle değerlendirebilirsin.

**[English README →](README.md)**

---

## Ne yapar

BIST kapanışından sonra `bist_ema_scanner.py`'yi çalıştırırsın. Seçtiğin endeksteki (varsayılan XU100, alternatif XU500) her hisse için Yahoo Finance'tan son 6 ayın günlük mumlarını çeker, EMA-20 ve EMA-50'yi hesaplar, ve bugünkü kapanışı iki kırılım örüntüsünden birine uyan hisseleri ekrana basar. Bulunan sinyaller bir CSV'ye eklenir; geçmişteki her sinyalin sonraki 1-10 günlük getirisi, gün-içi range bilgisi, hacim sürekliliği, piyasaya göre rölatif performansı, trend yaşı ve likidite profili de yeni günler geçtikçe otomatik olarak doldurulur.

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

### İşlem takvimi kurulumu

Tarayıcı, sinyal sonrası takip günlerini (d1..d10) hesaplarken hafta sonları ve resmi tatil günlerini doğru şekilde atlamak için açık bir BIST işlem takvimi kullanır. İki dosya gerekir:

- **`bist_calendar.py`** — takvim yardımcı modülü (kurulum gerektirmez; tarayıcı tarafından import edilir).
- **`bist_holidays.txt`** — kapalı ve yarım gün seanslarının manuel olarak tutulan listesi. Format: her satırda bir kayıt, `YYYY-MM-DD <closed|half_day> # opsiyonel yorum`. Resmî BIST takvimi yayımlandığında yılda bir güncelle.

Takvimi şu komutla doğrula:

```bash
python bist_calendar.py 2026-05-26
# Beklenen çıktı: tarihin işlem-günü statüsü, yarım gün bayrağı,
# bir sonraki işlem günü (bayram/hafta sonu duyarlı) ve d1..d5 dizisi.
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

Her çalıştırma aynı zamanda eski sinyallerin outcome verilerini de günceller — yeni seanslar geçtikçe eski satırların d_n kolonları otomatik dolar.

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

outcomes_xu100.csv         ← sinyal sonrası d1..d10 getirileri + gün-içi + piyasaya rölatif
outcomes_xu500.csv
```

### `signals_log_xu*.csv`

Sadece eklenen geçmiş kayıt dosyası. Sütunlar:

| Sütun | Anlamı |
|-------|--------|
| `scan_date`, `signal_date`, `ticker`, `trigger` | Taramanın çalıştığı tarih, seans tarihi, ticker, BRK/GDN |
| `y_close`, `y_ema20`, `y_ema50` | Dünkü kapanış ve EMA değerleri |
| `open`, `close`, `t_ema20`, `t_ema50` | Bugünkü açılış/kapanış ve EMA değerleri |
| `break_pct`, `vol_ratio` | Üst EMA üstündeki yüzde mesafe; bugünkü hacim / 20 günlük ortalama |
| `day_of_week` | Gün adı (Mon/Tue/…) — haftalık etki analizi için |
| `ema_gap_pct` | EMA20-EMA50 farkı, EMA50'nin % olarak; işareti trend istifini gösterir |
| `days_above_ema20`, `days_above_ema50` | Trend yaşı — sinyal günü dahil, kapanışın her EMA'nın üstünde kaldığı ardışık işlem günü sayısı |
| `avg_tl_volume_20d` | Sinyalden önceki 20 günün ortalama TL hacmi (close × volume); hissenin parasal likiditesi |
| `kap_count_14d`, `kap_oda_count_14d`, `kap_signal_day` | KAP bildirim sayıları (v1.12): son 14 takvim günündeki toplam, yalnızca ODA tipi ve sinyal gününün kendisindeki |
| `kap_type_breakdown`, `kap_category_breakdown` | KAP bildirim özetleri (v1.12): KAP'ın kendi tipine göre (`ODA:3 CA:1 …`) ve başlık-temelli kategoriye göre (`YENI_IS:2 …`) kompakt sayımlar |
| `ema20_slope`, `ema50_slope` | EMA trend eğimi (v1.13): her EMA'nın önceki 5 işlem günündeki % değişimi; işaret/büyüklük istifin yükselip yükselmediğini ve ne hızda olduğunu gösterir |
| `atr14`, `atr_pct`, `break_atr`, `ema_gap_atr` | ATR(14) + ATR-normalize giriş geometrisi (v1.14): Wilder ATR (mutlak), ATR'nin close'a oranı (%), ve üst EMA üstündeki uzamanın / EMA20-EMA50 farkının ATR cinsinden ifadesi |

`(signal_date, ticker)`'a göre mükerrer kayıt korumalı (v1.15) — logda zaten olan bir sinyal tekrar eklenmez; tarayıcıyı aynı gün ya da sonraki bir gün kaç kez çalıştırırsan çalıştır sorun olmaz. (v1.15 öncesi dedup anahtarında `scan_date` da vardı; bu yüzden değişmemiş bir seansı sonraki bir günde yeniden tarayınca mükerrer satır oluşuyordu — eski logları bir kez `dedup_signals.py` ile temizle.)

**KAP bildirim bağlamı (v1.12, yalnızca signals_log).** Beş `kap_*` kolonu, her sinyali son dönem Borsa İstanbul bildirim aktivitesiyle etiketler; veriyi opsiyonel bir `kap_lookup.py` modülü çeker. Tüm bildirim tipleri sayılır (ODA, CA, FR, DUY, DG, FON) — yalnızca özel durumlar değil — çünkü finansal raporlar, kurumsal işlemler ve duyuruların hepsi bir kırılımı etkileyebilir; mekanik bedelsiz (split) duyuruları, sayımı yanıltmasın diye hariç tutulur. İki özet dize, KAP'ın altı kendi tipine göre ve daha ince başlık-temelli kategoriye göre sayım verir. Tarama anında hiçbir edge/tier etiketi uygulanmaz — sayımlar mekaniktir; kategori-getiri eşleştirmesi, doğrulanmamış hipotezleri pipeline'a gömüp döngüsellik yaratmamak için biriken veri üzerinde ayrı bir analiz adımıdır. Zarif bozulma: `kap_lookup.py` yoksa veya KAP API'sine ulaşılamazsa, beş kolon boş yazılır ve tarama normal sürer.

### `outcomes_xu*.csv`

Kendi kendini güncelleyen dosya. Yeni sinyaller boş outcome hücreleriyle eklenir. Sonraki çalıştırmalarda tarayıcı şunları doldurur:

**Günlük getiriler (d1..d10).** Sinyal sonrası ilk 10 işlem günü için `signal_close`'a göre kapanış-kapanış yüzde getiri. `d1` ek olarak tam açılış ve kapanış fiyatlarıyla saklanır; böylece ertesi gün açılışında alarak elde edebileceğin **gerçek getiri** ölçülebilir.

**Gün-içi range (d1..d5).** `d_n_high_pct` ve `d_n_low_pct` her günün tepe ve tabanını `signal_close`'a göre yüzde olarak verir. Günlük kapanışla birlikte ilk 5 seansın tam OHLC'si yeniden inşa edilebilir.

**Hacim sürekliliği (d1..d5).** `d_n_vol_ratio` her günün hacmi / sinyal-öncesi 20 günün ortalama hacmi. Sinyal-günü `vol_ratio` ile aynı taban kullanıldığı için sinyal sonrası hacim akışı **elma-elma** karşılaştırılabilir.

**5 günlük uç değerler.** `max_5d_close` / `max_5d_pct` — 5 seans içindeki en yüksek kapanış. `min_5d_close` / `min_5d_pct` — en düşük kapanış; tüccarın oturarak kaldığı drawdown.

**Range içi kapanış pozisyonu.** `signal_close_in_range` ve `d1_close_in_range` — her günün kapanışının gün-içi range içinde nerede olduğu, [0, 1] ölçeğinde. 0 = günün tabanında kapanış (zayıf), 1 = günün tepesinde kapanış (güçlü). Mum range'i yoksa boş (limit-locked). d1 versiyonu ertesi gün kapanışında bilinen bir hold/exit sinyali; sinyal versiyonu giriş anında bilgi.

**Piyasaya rölatif referans.** Sinyal günü `xu100_open` ve `xu100_close`, ertesi işlem günü `xu100_d1_open` ve `xu100_d1_close`, ek olarak `xu100_d2_close`, `xu100_d3_close`, `xu100_d4_close`, `xu100_d5_close` — d2..d5 günlerinin her birinde BIST 100 endeks kapanışı. Bu kolonlar birlikte, sinyalin piyasaya rölatif getirisini d1'den d5'e kadar her ufukta endeksi yeniden çekmeden hesaplamanı sağlar. d1 referansıyla `rel_d1 = d1_pct − mkt_d1` (burada `mkt_d1 = (xu100_d1_close / xu100_close − 1) × 100`); d2..d5 kapanışları aynı hesabı tüm outcome penceresine taşır. d2..d5'in açılışları bilinçli olarak dahil edilmedi: kümülatif getiriler sinyal günü kapanışından başlayarak sadece kapanış-kapanış'a ihtiyaç duyar, açılışlar kullanılmazdı. Her d_n tarihi BIST işlem takvimine bağlı hesaplanır (yfinance'in N pozisyon sonraki satırına değil) — böylece bayram ve hafta sonu boşlukları off-by-N hatalarına yol açmaz.

**Trend yaşı.** `days_above_ema20` ve `days_above_ema50` — sinyal günü dahil, kapanışın her EMA'nın üstünde kaldığı ardışık işlem günü sayısı. `signals_log_*.csv` dosyasındaki aynı isimli kolonların aynası; sinyal anında tohumlanır, outcome güncellemeleri tarafından değiştirilmez. Sinyal günü tetikleyici tanımı gereği daima 1 sayılır (kapanış iki EMA'nın üstünde olmak zorunda). Taze kırılımları (=1) olgun trendlerden ayırt etmeyi sağlar; `days_above_ema50 − days_above_ema20` farkı, son zamanlarda sığ bir EMA20 geri çekilmesi yaşamış olgun yukarı trendleri işaretler.

**Trend eğimi (v1.13).** `ema20_slope` ve `ema50_slope` — her EMA'nın sinyal gününde önceki 5 işlem günündeki (`EMA_SLOPE_LOOKBACK`) yüzde değişimi: pozitif değer EMA'nın yükseldiğini gösterir. `signals_log` dosyasındaki aynı isimli kolonların aynası; sinyal anında bir kez tohumlanır, sonradan doldurulmaz. `ema_gap_pct` EMA istifinin boğa yönünde dizildiğini (post-cross) gösterirken, eğim bu yapının hızlanıyor mu yoksa düzleşiyor mu olduğunu gösterir — post-cross edge'ini, yükselen istife giren kırılımları düzleşen istife girenlerden ayırarak inceltmeyi amaçlar. Fiyat seviyesinden bağımsız kıyaslanabilsin diye % olarak ifade edilir (`ema_gap_pct` ile aynı mantık). Sinyal gününden önce yeterli geçmiş yoksa boş kalır.

**ATR-normalize giriş geometrisi (v1.14).** `atr14`, 14 günlük Wilder-yumuşatmalı Average True Range'dir (mutlak fiyat birimi); `atr_pct` ise `atr14 / close × 100`, yani hissenin tipik günlük salınımı yüzde olarak. `break_atr` ve `ema_gap_atr`, mevcut `break_pct` ve `ema_gap_pct`'i ATR cinsinden yeniden ifade eder — üst EMA üstündeki uzama ve EMA20-EMA50 farkı, ATR sayısı olarak. Amaç volatilite-kıyaslanabilirliği: ham giriş-anında-bilinen geometride `break_pct` ileri getiriye karşı monoton değildi (3-5% kovası en zayıf, >5% en güçlü), çünkü sabit bir %, düşük-vol vs yüksek-vol isimde çok farklı anlama gelir; "kaç ATR" ölçüsü, ham %'nin ayıramadığını ayırmalı. Her iki logda aynalanır, sinyal anında bir kez tohumlanır. Slope-ATR ayrı saklanmaz çünkü `ema20_slope / atr_pct` ile türetilebilir. `atr14` ayrıca ileride ATR-ölçekli stop'un da tabanıdır.

**Likidite.** `avg_tl_volume_20d` — (close × volume) değerinin 20 günlük yuvarlanan ortalaması, 1 gün shift edilmiş. `signals_log_*.csv` dosyasındaki aynı isimli kolonun aynası; sinyal anında tohumlanır, outcome güncellemeleri tarafından değiştirilmez. Hissenin son dönemdeki **parasal likiditesini** Türk lirası cinsinden temsil eder — bir tüccarın bir seansta gerçekçi olarak hareket ettirebileceği büyüklük. Hisse sayısı bazlı değil TL bazlıdır çünkü evren çapında fiyat ölçekleri çok farklı (1 TL'lik hissedeki 1M lot ile 1000 TL'lik hissedeki 1M lot çok farklı likiditelerdir). Analiz cohortlarını sulandıran mikro-likit uç vakaları filtrelemek için kullanılır.

**Durum bayrakları.** `at_limit` — d1 BIST ±%10 fiyat limitine takıldıysa "T". `split_suspect` — d1 OHLC ile `signal_close` arasında ölçek tutarsızlığı varsa "T" (sinyal anı ile outcome güncellemesi arasında hissede bölünme olduğunun parmak izi). Split-suspect satırlar analizlerde dışlanmalı: `df[df['split_suspect'] != 'T']`.

Birkaç hafta sonra bu dosya analiz için altın değerinde olur: Excel veya pandas'ta aç, `trigger`'a göre, `vol_ratio` aralıklarına göre, `break_pct` quintile'larına göre, gap büyüklüğüne göre (`d1_open - signal_close`), `close_in_range` pozisyonuna göre, `day_of_week`'e göre, `days_above_ema20` bandına göre, `ema20_slope` işaret/büyüklüğüne göre, `break_atr` / `atr_pct`'e göre (volatilite-normalize geometri), `avg_tl_volume_20d` decile'ına göre, KAP aktivitesine göre (`kap_signal_day`, `kap_category_breakdown` — signals_log'dan birleştirilerek) veya d1'den d5'e kadar herhangi bir ufukta piyasa-rölatif performansa göre pivot çek ve hangi koşulların gerçekten pozitif getiri öngördüğünü gör.

## Veri kalitesi ve dayanıklılık

Tarayıcı, outcomes log'unu sessizce bozabilecek birkaç yfinance veri tuhaflığını otomatik olarak tespit edip düzeltir:

- **Tatil-gap d1 placeholder'ı** — `signal_date == today` olduğunda ve araya tatil girdiğinde, yfinance d1 için `open == close == signal_close` ve sıfır high/low olan sahte bir bar dönebilir. Tespit edilir ve sonraki koşumda temizlenir.
- **Forward-fill duplikat zincirleri** — yfinance kapalı pazar günleri (bayram, atlanmamış hafta sonu) için bazen aynı barı duplikat döndürür. Takvim duyarlılığı olmadan bunlar geçerli d2, d3, … değerleri olarak saklanır. Tarayıcı 3+ ardışık özdeş `d_n_pct` çalıştırmalarını tespit edip temizler.
- **Gelecek-tarih placeholder'ı** — yfinance henüz işlem görmemiş tarihler için placeholder bar dönebilir. Per-day fill loop'undaki gelecek-tarih kontrolü bunların yazılmasını engeller.
- **Bayat forward-fill barlar** — sıfır hacim VE sıfır gün-içi range olan barlar forward-fill artefaktıdır; refill sırasında reddedilir.
- **Bölünme ölçek tutarsızlığı** — sinyal_date ile sonraki bir outcome güncellemesi arasında hisse bölündüğünde, `signal_close` (sinyal anında alınmış) ve d1 OHLC (adjusted olarak yeniden çekilmiş) farklı ölçeklerde olur. `split_suspect = "T"` ile işaretlenip analiz filtrelerinde dışlanır.

## Şema göçleri (schema migrations)

İki log dosyası da tarayıcı çalıştığında güncel şemaya otomatik olarak geçer. Sürümler arasında yeni kolonlar eklendiyse (örn. v1.6'da `signal_close_in_range`, v1.7'de `split_suspect`, v1.9'da `days_above_ema20` / `days_above_ema50`, v1.10'da `avg_tl_volume_20d`, v1.11'de `xu100_d2_close` / `xu100_d3_close` / `xu100_d4_close` / `xu100_d5_close`, v1.12'de `kap_*` kolonları ve v1.13'te `ema20_slope` / `ema50_slope`, v1.14'te `atr14` / `atr_pct` / `break_atr` / `ema_gap_atr`), tarayıcı bir sonraki koşumda "Migrating … adding columns […]" satırı basar ve dosyayı yeni başlıklarla yeniden yazar; mevcut satırların yeni kolonları boş olur. Göç öncesi veri olduğu gibi korunur. v1.11 kolonları özelinde, yeni piyasa-referans hücreleri tarayıcı sonraki işlem günlerinde çalıştıkça aşamalı olarak dolar — bir sonraki koşum anında d2..d5 tarihleri zaten geçmiş olan her sinyal tek bir geçişte doldurulur. v1.12, v1.13 ve v1.14 kolonları ise sinyal-anı bilgisidir, yalnızca yeni tespit edilen sinyallere tohumlanır; mevcut satırlar boş kalır (gerekirse yfinance geçmişinden tek seferlik bir backfill ile geriye dönük doldurulabilir).

## Tamamlayıcı araçlar

Ana tarayıcının yanında veri üreten opsiyonel scriptler. Her birinin kendi log dosyası vardır ve bağımsız çalıştırılabilir.

### `morning_snapshot.py` — gün-içi erken okuma

Bir önceki seansın sinyalleri için ilk ~50 dakikalık işlemi yakalar. Gap-up yönünün ve ilk-saat hacminin ertesi gün sonucunu kapanıştan önce onaylayıp onaylamadığını test etmek için yararlı. Çıktı: `morning_snapshots_xu*.csv`.

Açılıştan kısa süre sonra (yaklaşık 10:50 İstanbul saati) çalıştır:

```bash
python morning_snapshot.py            # XU100
python morning_snapshot.py -i xu500   # XU500
```

### `bist_signal_followup.py` — son sinyallerin hızlı istatistiği

En son sinyal tarihinin d1 sonuçlarını performansa göre sıralı şekilde, piyasaya rölatif özetle ekrana basar. Log dosyası yok; saf görüntüleme aracı.

```bash
python bist_signal_followup.py            # XU100
python bist_signal_followup.py -i xu500   # XU500
```

### `bist_mean_reversion_scanner.py` — alternatif strateji

Kapanışın EMA20/EMA50'den belirgin sapmalarını (yukarı veya aşağı) işaretleyen ikinci bir tarayıcı. Kendi log yapısı vardır ve 5 günlük sonuçları `mr_outcomes_xu*.csv` ile takip eder. Sinyalleri kırılım yerine mean-reversion merceğinden çapraz doğrulamak için kullanışlı.

```bash
python bist_mean_reversion_scanner.py            # XU100
python bist_mean_reversion_scanner.py -i xu500   # XU500
```

## Proje yapısı

```
bist-ema-scanner/
├── bist_ema_scanner.py             # Ana tarayıcı
├── bist_calendar.py                # BIST işlem-günü takvim yardımcısı
├── bist_holidays.txt               # Manuel tutulan tatil listesi
├── update_index.py                 # Hisse listesi yenileyici (KAP + Midas yedek)
├── debug_ticker.py                 # Tek hisse teşhis aracı
│
├── morning_snapshot.py             # Gün-içi erken okuma (tamamlayıcı)
├── bist_signal_followup.py         # Son sinyal hızlı istatistik (tamamlayıcı)
├── bist_mean_reversion_scanner.py  # Mean-reversion tarayıcısı (tamamlayıcı)
│
├── xu100.csv                       # Hisse listeleri (oluşturulur)
├── xu500.csv
├── signals_log_xu*.csv             # Sinyal geçmişi (oluşturulur)
├── outcomes_xu*.csv                # Sonuç takibi (oluşturulur)
├── morning_snapshots_xu*.csv       # Gün-içi snapshot'lar (oluşturulur)
├── mr_outcomes_xu*.csv             # Mean-reversion sonuçları (oluşturulur)
│
├── requirements.txt
├── LICENSE
├── README.md
└── README.tr.md
```

## Veri kaynakları

- **Hisse listeleri:** [KAP (Kamuyu Aydınlatma Platformu)](https://kap.org.tr/tr/Endeksler) — birincil. [Midas](https://www.getmidas.com/canli-borsa/) — yedek.
- **Fiyat geçmişi:** [Yahoo Finance](https://finance.yahoo.com/), `yfinance` kütüphanesi üzerinden, `auto_adjust=True` ile — yani EMA'lar temettü ve bedelsizlerden arındırılmış kapanışlar üzerinden hesaplanır.
- **İşlem takvimi:** `bist_holidays.txt` dosyasında manuel olarak tutulur.

## Sınırlamalar ve bilinen sorunlar

- **Yahoo veri gecikmesi:** BIST kapanışından ~15-30 dk sonra. Tarayıcıyı 18:30'dan önce çalıştırma, yoksa bugünün barı eksik gelir.
- **Düzeltilmiş fiyatlar ve bölünmeler:** Bir sinyal kaydedildikten sonra hisse bölündüğünde, `signal_close` ve d1 OHLC farklı ölçeklere düşer. Tarayıcı bunu tespit edip `split_suspect = "T"` koyar; downstream analizler bunları filtrelemelidir.
- **Borsa dışı kalan hisseler:** BIST'ten çıkarılan bir hisse için yfinance "possibly delisted" uyarısı verir. Üç aylık dengelemeden sonra `update_index.py`'yi tekrar çalıştırarak listeyi tazele.
- **Tatil takvimi bakımı:** `bist_holidays.txt` resmî BIST takvimi yayımlandığında yılda bir güncellenmek zorunda; yoksa yeni tatiller çevresindeki outcome'lar sessizce forward-filled barlara düşer.
- **Göç öncesi veri için boş hücreler:** Belirli bir kolon eklenmeden önce log'a yazılmış sinyaller o kolonda boş değer taşır. Şema kuşaklarını birleştirirken filtrele veya uygun şekilde doldur.
- **Al/sat tavsiyesi değildir.** Temel sinyal tek başına yaklaşık yazı-tura isabet oranındadır (crossover stratejilerinin tipik özelliği). Asıl avantaj filtrelerle (gap yönü, gün-içi kapanış pozisyonu, hacim sürekliliği, piyasa rejimi, sinyal sırası, trend yaşı, likidite, çok-günlü piyasa-rölatif performans) ve disiplinli pozisyon büyüklüğü/stop yönetimiyle birleştiğinde gelir — bu araç bunların hiçbirini içermez.

## Katkı

Issue ve pull request'ler memnuniyetle kabul edilir. Bir strateji değişikliği öneriyorsan (ör. yeni bir trigger tipi ya da yeni bir outcome kolonu), lütfen geçmiş `outcomes_xu*.csv` verisi üzerinden nasıl performans gösterdiğine dair kısa bir analiz ve falsifiable bir hipotez ifadesi (sonucun aşması beklenen önceden belirlenmiş bir eşik) ekle.

## Yasal uyarı

Bu yazılım yalnızca eğitim ve araştırma amaçlıdır. **Yatırım tavsiyesi değildir.** Yazar lisanslı bir yatırım danışmanı değildir. Borsa işlemleri zarar etme riski içerir; karar vermeden önce kendi araştırmanı yap ve yetkin bir profesyonele danış. Geçmiş performans — bu aracın ürettiği analizler dahil — gelecekteki sonuçları garanti etmez.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
