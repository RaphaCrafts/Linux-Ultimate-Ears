#!/usr/bin/env python3
"""Publish selectors and identities from successful local REA observations.

Intentionally excludes vendor source, raw results, phone serials and host paths.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    records = []
    failures = []
    for path in sorted(args.directory.glob('*.json')):
        record = json.loads(path.read_text())
        if record.get('ok') is False:
            failures.append({'local_record': path.name,
                             'error_type': record.get('error', {}).get('_tag')})
            continue
        record = record.get('value', record)
        if 'evidence_id' not in record:
            continue
        result = record.get('normalized_result', {})
        parameters = record.get('parameters', {})
        item = {
            'local_record': path.name,
            'evidence_id': record['evidence_id'],
            'operation': record['operation'],
            'apk_sha256': (record.get('subject') or {}).get('digest', {}).get('sha256'),
            'provider': record.get('provider'),
            'confidence': record.get('confidence'),
            'selectors': {k: parameters[k] for k in
                          ('class_name', 'method_name', 'overload_index', 'query')
                          if k in parameters},
        }
        for key in ('representation', 'body_status', 'fell_back', 'markers', 'coverage'):
            if key in result:
                item[key] = result[key]
        records.append(item)
    args.output.write_text(json.dumps({
        'scope': 'Static APK research except package extraction; raw evidence remains local.',
        'records': records, 'unsuccessful_probes': failures,
    }, indent=2) + '\n')
    print(f'Indexed {len(records)} records; {len(failures)} unsuccessful probes')


if __name__ == '__main__':
    main()
