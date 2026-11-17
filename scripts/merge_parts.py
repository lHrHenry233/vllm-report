#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge subagent shard files into one entries array (sha dedupe, commits order).

usage: merge_parts.py <YYYY-MM-DD> <out.json> <part1.json> [part2.json ...]
"""
import json, sys

ROOT = '/Users/henry/projects/vllm-report'
date, out_path, parts = sys.argv[1], sys.argv[2], sys.argv[3:]

order = [c['sha'][:10] for c in json.load(open(f'{ROOT}/data/vllm/commits/{date}.json', encoding='utf-8'))['commits']]
rank = {s: i for i, s in enumerate(order)}

seen, merged = {}, []
for p in parts:
    try:
        entries = json.load(open(p, encoding='utf-8'))
    except Exception as exc:
        print(f'SKIP {p}: {exc}')
        continue
    kept = 0
    for e in entries:
        k = e['sha'][:10]
        if k in seen:
            continue
        seen[k] = True
        merged.append(e)
        kept += 1
    print(f'{p}: +{kept}/{len(entries)}')

bad = [e['sha'][:10] for e in merged if e['sha'][:10] not in rank]
merged.sort(key=lambda e: rank.get(e['sha'][:10], 10 ** 6))
json.dump(merged, open(out_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
missing = [s for s in order if s not in seen]
print(f'merged={len(merged)} unknown_sha={len(bad)} pending_after_merge={len(missing)}')
if bad:
    print('unknown:', bad)
print('wrote', out_path)
