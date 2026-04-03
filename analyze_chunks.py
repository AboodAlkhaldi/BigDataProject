import pandas as pd
import os

# ── AYARLAR ────────────────────────────────────────────────────────────────────
FILE_PATH = "data.csv"      
CHUNK_SIZE = 100_000        
# ───────────────────────────────────────────────────────────────────────────────

print("=" * 55)
print("   BÜYÜK VERİ - CHUNK (PARÇA PARÇA) ANALİZİ")
print("=" * 55)
print(f"Dosya      : {FILE_PATH}")
print(f"Chunk boyutu: {CHUNK_SIZE:,} satır")
print(f"Dosya boyutu: {os.path.getsize(FILE_PATH) / (1024**2):.1f} MB")
print("-" * 55)

chunk_means = []   # Her chunk'ın ortalamasını buraya topluyoruz
total_rows  = 0
chunk_index = 0

# Dosyayı tek seferde değil, parça parça oku
for chunk in pd.read_csv(FILE_PATH, chunksize=CHUNK_SIZE):

    chunk_index += 1
    total_rows  += len(chunk)

    # Sayısal sütunların ortalaması
    numeric_cols = chunk.select_dtypes(include="number")
    mean_of_chunk = numeric_cols.mean()
    chunk_means.append(mean_of_chunk)

    print(f"Chunk {chunk_index:>3}  |  {len(chunk):>7,} satır okundu  |  Toplam: {total_rows:>10,}")

# Tüm chunk ortalamalarından genel istatistik çıkar
print("\n" + "=" * 55)
print("   GENEL İSTATİSTİKLER (tüm chunk'ların ortalaması)")
print("=" * 55)

overall = pd.DataFrame(chunk_means).mean()
print(overall.to_string())

print("\n" + "-" * 55)
print(f"Toplam okunan satır sayısı : {total_rows:,}")
print(f"Toplam chunk (parça) sayısı: {chunk_index}")
print("Analiz tamamlandı.")
print("=" * 55)