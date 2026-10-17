#!/usr/bin/env python3
"""Export factual legacy command IDs from REA static-initializer evidence.

Reads pinned JADX smali, never executes vendor code. Output is a name/number
catalogue, not a redistribution of the decompiled implementation.
"""
import argparse
import json
import re
from pathlib import Path


def extract(record):
    record = record.get('value', record)
    if record.get('operation') != 'inspect_android_method':
        raise ValueError('Expected REA inspect_android_method evidence')
    result = record['normalized_result']
    if (result.get('class_name') !=
            'com.logitech.ue.centurion.legacy.spp.centurion.CenturionCommand'
            or result.get('method', {}).get('name') != '<clinit>'
            or result.get('representation') != 'smali'
            or result.get('source', {}).get('status') != 'complete'):
        raise ValueError('Expected complete CenturionCommand initializer smali')
    registers = {}
    commands = {}
    for line in result['source']['text'].splitlines():
        match = re.search(r'const-string (v\d+), "([^"]+)"', line)
        if match:
            registers[match[1]] = match[2]
        match = re.search(r'const/(?:16|4) (v\d+), (-?0x[\da-f]+)', line)
        if match:
            registers[match[1]] = int(match[2], 16)
        match = re.search(
            r'invoke-direct \{([^}]+)\}.*CenturionCommand;-><init>', line)
        if match:
            args = match[1].split(', ')
            if len(args) != 4:
                raise ValueError('Unexpected constructor argument count')
            name, code = registers[args[1]], registers[args[3]]
            if not isinstance(name, str) or not isinstance(code, int):
                raise ValueError('Unresolved command constructor registers')
            if name in commands:
                raise ValueError('Duplicate command name')
            commands[name] = code
    if not commands or commands.get('Acknowledge') != 0 or commands.get('UNKNOWN') != -1:
        raise ValueError('Incomplete or unrecognized command initializer')
    return record, commands


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    record, commands = extract(json.loads(args.evidence.read_text()))
    result = {
        'apk_sha256': record['subject']['digest']['sha256'],
        'evidence_id': record['evidence_id'],
        'class': record['normalized_result']['class_name'],
        'scope': 'Static IDs; presence does not prove speaker support or payload semantics.',
        'commands': [{'name': name, 'code': code,
                      'hex': f'0x{code:04x}' if code >= 0 else None}
                     for name, code in commands.items()],
    }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Exported {len(commands)} command IDs to {args.output}')


if __name__ == '__main__':
    main()
