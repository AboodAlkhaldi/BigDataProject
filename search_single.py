"""
Basit ve tek dosyadan oluşan arama aracı.
Kullanım:
  python search_single.py --stats        # Yükleme ve istatistikleri göster
  python search_single.py               # Konsol arayüzü
  python search_single.py --partition   # Zorla partisyonlama

Not: `index.json` varsa, partisyonlama atlanır.
"""
import os
import json
import time
from pathlib import Path
import pandas as pd
import argparse

CSV_PATH = "data.csv"
PARTITION_DIR = "data"
INDEX_FILE = "index.json"
CHUNK_SIZE = 100_000

_cache = {}


def build_index(csv_path=CSV_PATH, partition_dir=PARTITION_DIR, index_file=INDEX_FILE, chunk_size=CHUNK_SIZE):
    """CSV'yi yıl/ay partisyonlarına böl ve index.json oluştur."""
    p_dir = Path(partition_dir)
    p_dir.mkdir(exist_ok=True)
    index = {}
    total = 0
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        total += len(chunk)
        # tarih
        if 'dispatch_date' in chunk.columns:
            chunk['dispatch_date'] = pd.to_datetime(chunk['dispatch_date'], errors='coerce')
            chunk = chunk.dropna(subset=['dispatch_date'])
            chunk['year'] = chunk['dispatch_date'].dt.year.astype(int)
            chunk['month'] = chunk['dispatch_date'].dt.month.astype(int)
        else:
            # Eğer tarih yoksa tümü tek partisyona koy
            chunk['year'] = 0
            chunk['month'] = 0

        for (y, m), g in chunk.groupby(['year', 'month']):
            key = f"{y}/{m:02d}"
            folder = p_dir / str(y) / f"{m:02d}"
            folder.mkdir(parents=True, exist_ok=True)
            parquet = folder / 'data.parquet'
            # Eğer varsa mevcutü oku ve birleştir (basit)
            if parquet.exists():
                existing = pd.read_parquet(parquet)
                g = pd.concat([existing, g], ignore_index=True)
            g.to_parquet(parquet, index=False, compression='snappy')
            # update index
            if 'objectid' in g.columns:
                min_id = int(g['objectid'].min())
                max_id = int(g['objectid'].max())
            else:
                min_id = None
                max_id = None
            index[key] = {
                'file_path': str(parquet),
                'count': int(len(g)),
                'min_id': min_id,
                'max_id': max_id,
                'min_date': str(g['dispatch_date'].min().date()) if 'dispatch_date' in g.columns else None,
                'max_date': str(g['dispatch_date'].max().date()) if 'dispatch_date' in g.columns else None,
            }
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2)
    return index


def load_index(index_file=INDEX_FILE):
    if not Path(index_file).exists():
        raise FileNotFoundError(f"Index not found: {index_file}")
    with open(index_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_partition(key, index):
    if key in _cache:
        return _cache[key]
    path = index[key]['file_path']
    df = pd.read_parquet(path)
    if 'dispatch_date' in df.columns:
        df['dispatch_date'] = pd.to_datetime(df['dispatch_date'], errors='coerce')
    _cache[key] = df
    return df


def search_by_id(object_id, index):
    res = []
    for key, meta in index.items():
        if meta.get('min_id') is None:
            continue
        if meta['min_id'] <= object_id <= meta['max_id']:
            df = _load_partition(key, index)
            found = df[df['objectid'] == object_id]
            if not found.empty:
                res.append(found)
    if res:
        return pd.concat(res, ignore_index=True)
    return None


def search_by_date(start_date, end_date, index):
    s = pd.to_datetime(start_date)
    e = pd.to_datetime(end_date)
    res = []
    for key, meta in index.items():
        if meta.get('min_date') is None:
            continue
        min_d = pd.to_datetime(meta['min_date'])
        max_d = pd.to_datetime(meta['max_date'])
        if max_d < s or min_d > e:
            continue
        df = _load_partition(key, index)
        filtered = df[(df['dispatch_date'] >= s) & (df['dispatch_date'] <= e)]
        if not filtered.empty:
            res.append(filtered)
    if res:
        return pd.concat(res, ignore_index=True)
    return None


def combined_search(object_id, start_date, end_date, index):
    # prefer id-based (usually faster)
    candidate = search_by_id(object_id, index) if object_id is not None else None
    if candidate is not None and start_date and end_date:
        s = pd.to_datetime(start_date)
        e = pd.to_datetime(end_date)
        candidate = candidate[(candidate['dispatch_date'] >= s) & (candidate['dispatch_date'] <= e)]
        return candidate if not candidate.empty else None
    if object_id is not None and candidate is None:
        # fallback to date-based
        return search_by_date(start_date, end_date, index)
    return candidate


def print_stats(index):
    total = sum(int(v['count']) for v in index.values())
    parts = len(index)
    years = sorted({k.split('/')[0] for k in index.keys()})
    print(f"Toplam partisyon: {parts}")
    print(f"Toplam kayıt: {total:,}")
    print("Yıllar:", ', '.join(years))


def cli_loop(index):
    while True:
        print('\n1) ID ile ara  2) Tarih aralığı  3) ID+Tarih  4) İstatistik  5) Çıkış')
        choice = input('Seçiminiz: ').strip()
        if choice == '1':
            try:
                oid = int(input('Object ID: ').strip())
            except ValueError:
                print('Geçersiz ID')
                continue
            t0 = time.time(); res = search_by_id(oid, index); dt = (time.time()-t0)*1000
            if res is None:
                print('Sonuç yok')
            else:
                print(res.head(10).to_string(index=False))
            print(f'İşlem süresi: {dt:.2f} ms')
        elif choice == '2':
            sd = input('Başlangıç (YYYY-MM-DD): ').strip(); ed = input('Bitiş (YYYY-MM-DD): ').strip()
            t0 = time.time(); res = search_by_date(sd, ed, index); dt = (time.time()-t0)*1000
            if res is None:
                print('Sonuç yok')
            else:
                print(f'{len(res)} sonuç bulundu')
                print(res.head(10).to_string(index=False))
            print(f'İşlem süresi: {dt:.2f} ms')
        elif choice == '3':
            try:
                oid = int(input('Object ID: ').strip())
            except ValueError:
                print('Geçersiz ID'); continue
            sd = input('Başlangıç (YYYY-MM-DD): ').strip(); ed = input('Bitiş (YYYY-MM-DD): ').strip()
            t0=time.time(); res = combined_search(oid, sd, ed, index); dt=(time.time()-t0)*1000
            if res is None:
                print('Sonuç yok')
            else:
                print(res.head(10).to_string(index=False))
            print(f'İşlem süresi: {dt:.2f} ms')
        elif choice == '4':
            print_stats(index)
        elif choice == '5':
            break
        else:
            print('Geçersiz seçim')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--partition', action='store_true', help='Zorla partisyonlama yap')
    parser.add_argument('--stats', action='store_true', help='İndeks yükle ve istatistik göster')
    args = parser.parse_args()

    if not Path(INDEX_FILE).exists() or args.partition:
        print('İndeks bulunamadı veya --partition verildi. Partisyonlama başlıyor...')
        try:
            build_index()
        except Exception as e:
            print('Partisyonlama hata:', e)
            return
    try:
        index = load_index()
    except Exception as e:
        print('İndeks yüklenemedi:', e)
        return

    if args.stats:
        print_stats(index)
        return

    cli_loop(index)

if __name__ == '__main__':
    main()
