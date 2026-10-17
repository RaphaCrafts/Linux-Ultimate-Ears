#!/usr/bin/env python3
"""Collect product packshots from official UE pages, preserving source attribution."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

MODELS = ['megaboom-3', 'boom-3', 'megaboom-4', 'boom-4',
          'everboom-bluetooth', 'epicboom-bluetooth', 'hyperboom', 'wonderboom-4']

def read(url):
    with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as response:
        return response.read()

def collect(model):
    page = 'https://www.ultimateears.com/en-us/shop/p/' + model
    source = read(page).decode()
    records = []
    for text in re.findall(r'<script type="application/ld\+json">(.*?)</script>', source, re.S):
        schema = json.loads(text)
        for item in schema if isinstance(schema, list) else [schema]:
            for variant in item.get('model', []):
                images = variant.get('image', [])
                if images:
                    records.append({'model': model.replace('-bluetooth', ''),
                                    'colour': variant['color'], 'sku': variant.get('sku'),
                                    'source_page': page, 'source_image': images[0],
                                    'label_source': 'Official product page structured data'})
    return records

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('assets/speakers'))
    parser.add_argument('--legacy-colours', action='store_true',
                        help='Also probe historical official CDN filenames for generation 3')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    page_failures = []
    existing = {}
    manifest_path = args.output / 'manifest.json'
    if manifest_path.exists():
        existing = {(r['model'],r['colour'].lower()):r for r in json.loads(manifest_path.read_text())['images']}
    for model in MODELS:
        try:
            records.extend(collect(model))
        except Exception as error:
            page_failures.append({'model':model,'error':str(error)})
    if args.legacy_colours:
        for model in ['megaboom-3', 'boom-3']:
            for slug, label in [('night-black', 'Night black'), ('lagoon-blue', 'Lagoon blue'),
                                ('sunset-red', 'Sunset red'), ('ultraviolet-purple', 'Ultraviolet purple'),
                                ('unicorn', 'Unicorn pink'), ('moon','Moon'), ('dusk','Dusk'),
                                ('jungle-grey','Jungle grey'), ('seashell-peach','Seashell peach'),
                                ('denim','Denim'), ('cloud','Cloud'), ('urban-magenta','Urban magenta')]:
                if any(r['model'] == model and r['colour'].lower() == label.lower() for r in records):
                    continue
                filename = f"ue-{model.replace('-', '')}-{slug}-front.png"
                records.append({'model': model, 'colour': label, 'sku': None,
                                'source_page': 'https://www.ultimateears.com/en-us/shop/p/' + model,
                                'source_image': f'https://resource.ultimateears.com/content/dam/ue/products/wireless-speakers/{model}/{slug}/{filename}',
                                'label_source': 'Historical official CDN filename; not a current shop listing'})
    def download(record):
        key = (record['model'],record['colour'].lower())
        if key in existing and (args.output / existing[key]['file']).is_file():
            return existing[key]
        try:
            original = record['source_image']
            path = '/content/dam/' + original.split('/content/dam/', 1)[1]
            url = 'https://resource.ultimateears.com/w_600,h_600,c_fit,f_webp,q_auto' + path
            data = read(url)
            if not (data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
                raise ValueError('Response is not a WebP')
            colour = re.sub(r'[^a-z0-9]+', '-', record['colour'].lower()).strip('-')
            name = f"{record['model']}-{colour}.webp"
            (args.output / name).write_bytes(data)
            return {**record, 'file': name, 'download_url': url,
                    'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
        except Exception as error:
            return {**record, 'error': str(error)}
    results = list(ThreadPoolExecutor(max_workers=6).map(download, records))
    success_map = dict(existing)
    success_map.update({(r['model'],r['colour'].lower()):r for r in results if 'file' in r})
    success = list(success_map.values())
    failures = [r for r in results if 'error' in r]
    manifest = {'retrieved_on': datetime.now(timezone.utc).date().isoformat(), 'rights_holder': 'Logitech / Ultimate Ears',
                'licence': 'Third-party product imagery; no open-source licence asserted.',
                'scope': 'Retrieved official packshots, not an exhaustive historical colour or device support list.',
                'images': success, 'unavailable': failures, 'page_failures':page_failures}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'{len(success)} verified images across {len(set(r["model"] for r in success))} models; {len(failures)} unavailable')
    for r in failures:
        print(r['model'], r['colour'], r['error'])

if __name__ == '__main__':
    main()
