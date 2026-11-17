#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append analysis entries (given by 10-char sha prefix) to data/vllm/analysis/<date>.json.

usage: add_entries.py <YYYY-MM-DD> <entries.json>
"""
import json, os, sys

ROOT = '/Users/henry/projects/vllm-report'
SIGS = {'sig-core', 'sig-large-scale-serving', 'sig-model-performance', 'sig-spec-decode',
        'sig-quantization', 'sig-omni', 'sig-rl', 'sig-ci', 'other'}
TYPES = {'bugfix', 'feature', 'performance', 'refactor', 'test', 'docs', 'ci', 'chore',
         'dependency-bump', 'revert', 'deprecation'}
RISKS = {'low-risk', 'medium-risk', 'high-risk'}

date, ep = sys.argv[1], sys.argv[2]
cpath = f'{ROOT}/data/vllm/commits/{date}.json'
apath = f'{ROOT}/data/vllm/analysis/{date}.json'

commits = json.load(open(cpath, encoding='utf-8'))['commits']
order = [c['sha'] for c in commits]
prefix = {s[:10]: s for s in order}

raw = json.load(open(ep, encoding='utf-8'))
data = json.load(open(apath, encoding='utf-8')) if os.path.exists(apath) else {
    'date': date, 'repo': 'vllm-project/vllm', 'generated_at': '',
    'daily_summary': '', 'sig_summaries': {}, 'commits': []
}
have = {c['sha'] for c in data['commits']}

added = 0
for e in raw:
    p = e['sha'][:10]
    if p not in prefix:
        sys.exit(f'ERROR: sha {p} not in {date} commits')
    sha = prefix[p]
    if sha in have:
        continue
    assert e['sig'] in SIGS, f'{p}: bad sig {e["sig"]}'
    tags = e['tags']
    assert isinstance(tags, list) and all(isinstance(t, str) for t in tags), f'{p}: tags must be strings'
    assert len(tags) >= 4, f'{p}: need >=4 tags, got {len(tags)}'
    assert tags[0] in TYPES, f'{p}: bad type {tags[0]}'
    assert tags[1] in RISKS, f'{p}: bad risk {tags[1]}'
    assert e['comment'].strip() and e['sig_reason'].strip(), f'{p}: empty comment/reason'
    data['commits'].append({'sha': sha, 'comment': e['comment'].strip(), 'sig': e['sig'],
                            'sig_reason': e['sig_reason'].strip(), 'tags': tags,
                            'pr_number': e.get('pr_number')})
    have.add(sha)
    added += 1

rank = {s: i for i, s in enumerate(order)}
data['commits'].sort(key=lambda c: rank[c['sha']])
json.dump(data, open(apath, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
missing = [s[:10] for s in order if s not in {c['sha'] for c in data['commits']}]
print(f'{date}: appended={added} total={len(data["commits"])}/{len(order)} missing={len(missing)}')
if missing and len(missing) <= 15:
    print('missing shas:', ' '.join(missing))
