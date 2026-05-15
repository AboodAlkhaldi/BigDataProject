# Suç Verisi Arama Sistemi — Proje Anlatımı

## 1. Proje Nedir?

Bu proje, Philadelphia şehrine ait büyük boyutlu bir **suç (crime) veri setini** verimli bir şekilde **arama, filtreleme ve sorgulama** amacıyla geliştirilmiş bir Python uygulamasıdır.

Elimizdeki ham veri, yaklaşık **836 MB** boyutunda tek bir CSV dosyasıdır (`data.csv`). Bu kadar büyük bir dosyayı her sorguda baştan sona okumak hem **çok yavaş** hem de **çok fazla RAM** kullanır. Bu yüzden veriyi mantıklı parçalara bölüp, hangi verinin nerede olduğunu bir **indeks (index) dosyasında** tutarak hızlı arama yapılmasını sağlıyoruz.

Kullanıcı, konsol üzerinden:
- **Object ID** ile bir suç kaydını bulabilir,
- **Tarih aralığı** ile o tarihler arasındaki tüm suçları listeleyebilir,
- **ID + Tarih** kombinasyonuyla birleşik arama yapabilir,
- Veri seti hakkında **istatistikler** alabilir.

---

## 2. Projenin Genel Mantığı (Neden Böyle Yaptık?)

### Sorun
- `data.csv` çok büyük (≈ 836 MB, milyonlarca satır).
- Pandas ile dosyanın tamamını `read_csv` ile belleğe almak hem yavaş hem de bilgisayarı kilitleyebilir.
- Her arama için tüm dosyayı taramak akıllıca değildir.
__
### Çözüm — Üç Aşamalı Yaklaşım

1. **Partisyonlama (Parçalara Ayırma):**
   Veri, **yıl/ay** bazında klasörlere bölünür. Örneğin 2023 yılının Mart ayına ait kayıtlar `data/2023/03/data.parquet` dosyasına yazılır.

2. **Parquet Formatı:**
   CSV yerine **Parquet** kullanılır. Parquet sütun bazlı, sıkıştırılmış (snappy) ve okuması CSV'den **kat kat hızlı** bir formattır. Aynı veri çok daha az yer kaplar.

3. **İndeks Dosyası (`index.json`):**
   Her partisyon (yıl/ay) için meta bilgiler tutulur:
   - Dosya yolu
   - Kaç kayıt var
   - En küçük ve en büyük `objectid`
   - En küçük ve en büyük `dispatch_date`

   Bu sayede bir arama yapıldığında **hangi parquet dosyalarını açmamız gerektiğini önceden biliyoruz** — gereksiz dosyalar hiç açılmaz.

### Neden index.json?
`index.json` adeta bir **kitabın içindekiler sayfası** gibidir. Bir kitapta "evrim" konusunu bulmak için tüm kitabı okumayız, içindekilere bakar, sayfaya gideriz. Aynı şekilde:
- ID 9026106 aranıyorsa, indekste `min_id ≤ 9026106 ≤ max_id` şartını sağlayan partisyon(lar) bulunur ve **yalnızca o dosya(lar)** açılır.
- Tarih aralığı sorgusunda da aynı mantıkla, sadece o tarih aralığını içeren ay klasörleri açılır.

Bu yöntem, **836 MB**'lık CSV'yi taramak yerine, çoğu zaman **birkaç MB**'lık tek bir parquet dosyasını okumayı yeterli hale getirir. Arama süresi **dakikalardan milisaniyelere** iner.

---

## 3. Dosya ve Klasör Yapısı (Anatomi)

```
crimes_updated.csv/
│
├── data.csv                  # Ham veri (yaklaşık 836 MB, orijinal CSV)
├── index.json                # Partisyon indeksi (hangi veri nerede?)
├── search_single.py          # Ana Python uygulaması (arama + partisyonlama)
├── analyze_chunks.py         # (Önceki sürümden kalan analiz script'i)
│
├── data/                     # Partisyonlanmış veri klasörü
│   ├── 2006/
│   │   ├── 01/
│   │   │   └── data.parquet  # 2006 Ocak ayı suçları
│   │   ├── 02/
│   │   │   └── data.parquet
│   │   └── ...               # 03 ... 12
│   ├── 2007/
│   │   └── ...
│   ...
│   └── 2023/
│       └── 12/
│           └── data.parquet
│
└── __pycache__/              # Python'un otomatik oluşturduğu önbellek
```

**Veri 2006'dan 2023'e kadar 18 yılı kapsar.** Her yıl 12 ay = toplamda yaklaşık **216 ayrı parquet dosyası**na bölünmüştür.

---

## 4. Her Dosyanın Görevi

### 4.1. `data.csv` — Ham Veri
- **Boyut:** ~836 MB
- **İçerik:** Philadelphia polisinin suç çağrı kayıtları.
- **Sütunlar (önemli olanlar):**
  - `objectid` — Her kaydın benzersiz kimliği
  - `dispatch_date` — Polisin olay yerine sevk edildiği tarih
  - `dispatch_time` — Sevk saati
  - `dc_dist` — Bölge kodu
  - `location_block` — Olay sokağı/bloğu
  - `text_general_code` — Suçun türü (örn. "Thefts", "Assaults")
  - `point_x`, `point_y` — Koordinatlar
  - `year`, `month`, `day`, `hour`, `dayOfWeek` — Tarih/saat bileşenleri
- **Neden duruyor?** Programın ilk çalıştırılışında bu dosyadan partisyonlar üretilir. Sonraki çalışmalarda zaten parquet'ler kullanıldığı için CSV'ye dokunulmaz.

### 4.2. `search_single.py` — Ana Uygulama
Projenin **kalbi** olan tek dosyalık Python aracıdır. İçinde şu fonksiyonlar vardır:

| Fonksiyon | Görevi |
|-----------|--------|
| `build_index()` | CSV'yi 100.000 satırlık parçalar (`chunk`) halinde okur, yıl/ay'a göre gruplar, parquet dosyaları yazar, indeksi oluşturur. |
| `load_index()` | `index.json` dosyasını belleğe yükler. |
| `_load_partition(key, index)` | Sadece istenen ay'ın parquet dosyasını okur ve önbelleğe alır (`_cache`). Aynı ay tekrar sorgulanırsa diskten okumaz. |
| `search_by_id(...)` | Bir `objectid` için yalnızca ilgili aralığı kapsayan partisyonları açar. |
| `search_by_date(...)` | Bir tarih aralığı için yalnızca o aralığa düşen partisyonları açar. |
| `combined_search(...)` | ID + Tarih birleşimiyle arama yapar. |
| `print_stats(...)` | Toplam partisyon, toplam kayıt ve yıl listesini yazdırır. |
| `cli_loop(...)` | Kullanıcıya menü gösterir, seçimini alır, ilgili fonksiyonu çağırır. |
| `main()` | Argümanları işler (`--partition`, `--stats`) ve uygun akışı başlatır. |

**Akıllı tasarım detayları:**
- **Chunk okuma:** CSV 100.000 satırlık parçalar halinde okunarak RAM patlaması engellenir.
- **Önbellek (`_cache`):** Aynı ay tekrar sorgulanırsa diskten okunmaz, RAM'den döner.
- **Tarih atlama:** `min_date`/`max_date` ile partisyonun sorguya hiç uymadığı durumda dosya açılmaz.
- **ID aralığı atlama:** `min_id`/`max_id` ile ID sorgularında aynı optimizasyon yapılır.

### 4.3. `index.json` — İndeks Dosyası
- **Boyut:** ~42 KB (çok küçük, hızlı yüklenir).
- **Yapısı:**
  ```json
  {
    "2023/03": {
      "file_path": "data\\2023\\03\\data.parquet",
      "count": 13745,
      "min_id": 96,
      "max_id": 9053427,
      "min_date": "2023-03-01",
      "max_date": "2023-03-31"
    },
    ...
  }
  ```
- **Görevi:** Hangi yıl/ay'ın hangi dosyada olduğunu, kaç kayıt içerdiğini ve ID/tarih aralıklarını söyler. Aramalarda **filtre** olarak kullanılır.

### 4.4. `data/` Klasörü — Partisyonlar
- Her `data/YYYY/MM/data.parquet` dosyası **o ay'a ait tüm suç kayıtlarını** tutar.
- **Parquet** seçiminin nedenleri:
  - **Sütun bazlı:** Sadece ihtiyacımız olan sütunları okuyabiliriz.
  - **Sıkıştırma (snappy):** CSV'ye göre **5–10 kat** daha küçük.
  - **Hız:** Pandas `read_parquet` ile çok hızlı yüklenir.
  - **Tip korunur:** Tarih, sayı, string tipleri parquet içinde saklı; her seferinde tekrar parse etmeye gerek kalmaz.

### 4.5. `analyze_chunks.py`
- Projenin önceki sürümünden kalan, CSV'yi chunk halinde analiz eden eski script. `search_single.py` bu işlevin daha gelişmiş halini içerdiği için artık ana akışta kullanılmaz.

### 4.6. `__pycache__/`
- Python'un otomatik oluşturduğu önbellek (`.pyc` dosyaları). Kodun bir parçası değildir, git tarafından da takip edilmez.

---

## 5. Çalışma Akışı (Programı Çalıştırınca Ne Olur?)

### İlk Çalıştırma
```
python search_single.py
```
1. Program `index.json` var mı diye bakar.
2. **Yoksa:** `build_index()` çalışır → `data.csv` okunur → yıl/ay'a göre bölünür → parquet'ler yazılır → `index.json` oluşturulur. (Bu işlem bir kere yapılır, birkaç dakika sürer.)
3. İndeks yüklenir.
4. Konsol menüsü açılır.

### Sonraki Çalıştırmalar
```
python search_single.py
```
1. `index.json` zaten var → partisyonlama atlanır.
2. İndeks anında belleğe yüklenir.
3. Menü açılır, kullanıcı arama yapar — sonuçlar **milisaniyeler içinde** döner.

### Diğer Komutlar
```
python search_single.py --stats        # Sadece istatistik göster
python search_single.py --partition    # Zorla yeniden partisyonla
```

---

## 6. Örnek Bir Arama Senaryosu

**Senaryo:** Kullanıcı `objectid = 9026106` numaralı kaydı arıyor.

1. Program `index.json`'daki tüm partisyonları gezer.
2. `min_id ≤ 9026106 ≤ max_id` koşulunu sağlayanları tespit eder. (Çoğu partisyon elenir.)
3. Yalnızca **birkaç** parquet dosyası açılır.
4. Pandas filtreleme ile satır bulunur.
5. Sonuç kullanıcıya gösterilir.

**Karşılaştırma:**
- CSV'yi taramak: ~836 MB okuma, dakikalar sürer.
- Bu sistem: birkaç MB okuma, **birkaç milisaniye**.

---

## 7. Kullanılan Teknolojiler ve Neden Seçildiler?

| Teknoloji | Neden? |
|-----------|--------|
| **Python** | Veri işleme için en yaygın ve okuması en kolay dil. |
| **pandas** | DataFrame yapısı sayesinde filtreleme, gruplama ve tarih işlemleri çok kolay. |
| **Parquet (pyarrow)** | Büyük veri için CSV'den çok daha hızlı ve küçük. |
| **JSON (index)** | İnsan tarafından okunabilir, hafif, her dilde desteklenir. |
| **argparse** | Komut satırı parametrelerini düzgün yönetmek için. |

---

## 8. Bu Projenin Öğrettikleri

Bu proje yalnızca bir "arama uygulaması" değil, aynı zamanda **büyük veri (big-data lite) problemlerinin nasıl çözüleceğine dair bir vaka çalışmasıdır**. Öğrenilen ana ilkeler:

1. **Veriyi bölmek (partitioning),** her zaman tamamını okumaktan daha hızlıdır.
2. **Doğru veri formatını seçmek** (CSV → Parquet) tek başına büyük performans kazandırır.
3. **İndeksleme**, gereksiz işten kaçınmanın en etkili yoludur — veritabanlarının da temel mantığıdır.
4. **Önbellek (caching)** tekrar eden işlemleri ücretsiz yapar.
5. **Lazy loading** (sadece gerektiğinde yükle) prensibi RAM'i akıllıca kullanır.

---

## 9. Özet

| Özellik | Değer |
|---------|-------|
| Ham veri | `data.csv` (~836 MB, 2006–2023) |
| Partisyon sayısı | ~216 (18 yıl × 12 ay) |
| Format | CSV → Parquet (snappy) |
| İndeks | `index.json` (~42 KB) |
| Ana script | `search_single.py` |
| Arama türleri | ID, Tarih, ID+Tarih |
| Tipik arama süresi | Milisaniyeler |

Sonuç olarak, klasik bir "tüm CSV'yi tara" yaklaşımının **dakikalar** sürdüğü iş, bu sistemde **milisaniyelere** indirilmiştir. Proje hem **performans optimizasyonu**, hem **veri mimarisi**, hem de **kullanıcı dostu CLI tasarımı** açısından bütünleşik bir çözüm sunar.
