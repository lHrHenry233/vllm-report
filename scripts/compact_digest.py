#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compact digest of pending commits (those without an analysis entry).

usage: compact_digest.py <YYYY-MM-DD> [count] [skip]
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not os.path.isdir(os.path.join(ROOT, 'data')):
    ROOT = '/Users/henry/projects/vllm-report'

date = sys.argv[1]
count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
skip = int(sys.argv[3]) if len(sys.argv) > 3 else 0

commits = json.load(open(f'{ROOT}/data/vllm/commits/{date}.json', encoding='utf-8'))['commits']
prs_path = f'{ROOT}/data/vllm/prs/{date}.json'
prs = {}
if os.path.exists(prs_path):
    prs = {c['sha'][:10]: c for c in json.load(open(prs_path, encoding='utf-8'))['commits']}
ana_path = f'{ROOT}/data/vllm/analysis/{date}.json'
done = set()
if os.path.exists(ana_path):
    done = {c['sha'][:10] for c in json.load(open(ana_path, encoding='utf-8'))['commits']}

pending = [c for c in commits if c['sha'][:10] not in done]
body = re.compile(r'https?://\S+')

out = []
for c in pending[skip:skip + count]:
    s = c['sha'][:10]
    msg = c.get('message') or ''
    title = msg.split('\n', 1)[0].strip()
    st = c.get('stats') or {}
    files = c.get('files') or []
    pr = prs.get(s, {})
    prn = pr.get('pr_number', '')
    head = f"### {s} | {title} | +{st.get('total_additions','?')}/-{st.get('total_deletions','?')}, {st.get('files_changed', len(files))} files"
    if prn:
        head += f" | PR#{prn}"
    out.append(head)
    names = [f.get('filename', '') for f in files][:8]
    if names:
        out.append('PATHS: ' + ', '.join(names))
    text = (pr.get('pr_body') or '')
    text = body.sub('', text)
    text = re.sub(r'[ \t]*\|?[ \t]*[-:]{3,}[ \t]*\|?[ \t]*(\|[^\n]*)?', '', text)
    text = re.sub(r'\n{2,}', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()
    if text:
        out.append(text[:900])
    out.append('')

print(f'{date}: pending={len(pending)} showing={min(count, max(0, len(pending)-skip))} skip={skip}', file=sys.stderr)
print('\n'.join(out))
