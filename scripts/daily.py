#!/usr/bin/env python3
"""Curate open-license Wikimedia Commons photographs and optionally analyze via Gemini.
No pip dependencies, no paid fallback, no hidden credential in git history.

Usage: python scripts/daily.py [--dry-run] [--max N]
Set GEMINI_API_KEY only if free tier access is confirmed on the user's account.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / 'data' / 'entries.json'
STATUS_FILE = ROOT / 'data' / 'status.json'
UA = os.getenv('WIKIMEDIA_USER_AGENT') or 'MikoAtelier/1.0 (personal visual-study project; https://github.com/)'
GEMINI_KEY = os.getenv('GEMINI_API_KEY', '').strip()
# Prefer a currently advertised free-tier model; override if your AI Studio plan differs.
MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.1-flash-lite').strip()
# No paid API key or automated billing fallback.
API_URL = 'https://commons.wikimedia.org/w/api.php'
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/'

SEARCHES = {
    'portrait': ['portrait photography featured', 'portrait photograph people', 'studio portrait photography'],
    'photography': ['landscape photography featured', 'street photography', 'architecture photograph', 'fine art photography'],
    'cinema': ['film production still photography', 'behind the scenes film set photograph', 'cinematography set photography'],
}
TARGET = {'portrait': 4, 'photography': 3, 'cinema': 1}
FREE_TIER_CONFIRMED = os.getenv('GEMINI_FREE_TIER_CONFIRMED', '').lower() == 'true'
AI_ENABLED = bool(GEMINI_KEY and FREE_TIER_CONFIRMED)
AI_STOPPED = False
ERRORS = []


def get(url: str, headers: dict | None = None, limit: int = 5_000_000) -> bytes:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, image/jpeg, image/png, image/webp, */*', **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Response too large')
        return data


def plain(value) -> str:
    if not value:
        return ''
    return html.unescape(re.sub(r'<[^>]+>', ' ', str(value))).strip()


def meta(info, key):
    field = info.get('extmetadata', {}).get(key)
    return str(field.get('value', '')) if isinstance(field, dict) else ''


def licensed(info) -> bool:
    lic = plain(meta(info, 'LicenseShortName')).lower()
    return bool(re.search(r'(cc\s*(?:by|0)|creative commons (?:attribution|zero)|public domain)', lic)) and not re.search('nc|nd|noncommercial|no derivatives', lic)


def resolve(item, category):
    title = item.get('title', '')
    imageinfo = (item.get('imageinfo') or [{}])[0]
    width = int(imageinfo.get('width') or 0)
    height = int(imageinfo.get('height') or 0)
    if width < 1000 or height < 650 or not .48 < width / height < 2.7 or not licensed(imageinfo):
        return None
    mime = imageinfo.get('mime', '')
    if mime not in ('image/jpeg', 'image/png', 'image/webp'):
        return None
    img = imageinfo.get('thumburl') or imageinfo.get('url')
    src = imageinfo.get('descriptionurl')
    if not img or not src or not img.startswith('https://'):
        return None
    if re.search(r'nudity|porn|explicit|erotic|sexual', title, flags=re.I):
        return None
    author = re.sub(r'\s+', ' ', plain(meta(imageinfo, 'Artist'))) or 'Wikimedia Commons contributor'
    lic = plain(meta(imageinfo, 'LicenseShortName'))[:90] or 'Open license'
    description = plain(meta(imageinfo, 'ImageDescription'))[:240]
    clean_title = re.sub(r'^File:', '', title, flags=re.I)
    clean_title = re.sub(r'\.(jpg|jpeg|png|webp)$', '', clean_title, flags=re.I)
    clean_title = clean_title.replace('_', ' ').strip()[:95]
    license_url = meta(imageinfo, 'LicenseUrl')
    if license_url and not license_url.startswith('https://'):
        license_url = ''
    return {
        'id': 'commons-'+str(item.get('pageid')),
        'title': clean_title,
        'artist': author,
        'description': description,
        'category': category,
        'image': img,
        'source': 'Wikimedia Commons',
        'sourceUrl': src,
        'license': lic,
        'licenseUrl': license_url,
        'credit': plain(meta(imageinfo, 'Credit')),
        'originalFile': title,
        'width': width,
        'height': height,
        'date': dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y-%m-%d'),
        'analysis': {},
    }


def search_commons(term, category, count=36):
    params = {
        'action': 'query', 'format': 'json', 'formatversion': '2',
        'generator': 'search', 'gsrnamespace': '6', 'gsrlimit': str(count),
        'gsrsearch': term, 'prop': 'imageinfo',
        'iiprop': 'url|size|mime|extmetadata', 'iiurlwidth': '1100',
    }
    url = API_URL + '?' + urllib.parse.urlencode(params)
    doc = json.loads(get(url).decode('utf-8'))
    pages = doc.get('query', {}).get('pages', [])
    return [x for entry in pages if (x := resolve(entry, category))]


def analyze(item):
    global AI_STOPPED
    if not AI_ENABLED or AI_STOPPED:
        return None
    try:
        content = get(item['image'], limit=3_000_000)
        if content.startswith(b'\x89PNG'):
            mime = 'image/png'
        elif content[:4] == b'RIFF' and content[8:12] == b'WEBP':
            mime = 'image/webp'
        elif content.startswith(b'\xff\xd8'):
            mime = 'image/jpeg'
        else:
            return None
        prompt = ('你是严谨的摄影学习编辑。基于实际画面，生成适合中文摄影爱好者的简洁学习卡片。'
                  '请只输出 JSON 对象，包含 lighting、composition、color、practice 四个字符串字段。'
                  '每个字段 30—90 个汉字，具体描述观察到的视觉事实与可复现的方法。'
                  '电影美术也从画面设计角度分析。不能编造镜头、机型、曝光参数、导演或摄影师创作意图。'
                  '无法确定的内容使用“可能”“看起来”等谨慎表述。')
        payload = {'contents': [{'parts': [
            {'text': prompt},
            {'inlineData': {'mimeType': mime, 'data': base64.b64encode(content).decode('ascii')}},
        ]}], 'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.35, 'maxOutputTokens': 1100}}
        url = GEMINI_URL + urllib.parse.quote(MODEL, safe='-._') + ':generateContent'
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), method='POST', headers={
            'Content-Type': 'application/json', 'x-goog-api-key': GEMINI_KEY, 'User-Agent': UA,
        })
        with urllib.request.urlopen(req, timeout=75) as resp:
            response = json.load(resp)
        message = response['candidates'][0]['content']['parts'][0]['text']
        result = json.loads(message.strip().strip('`').replace('json\n', '', 1))
        return {k: str(result[k])[:250] for k in ('lighting','composition','color','practice') if isinstance(result.get(k), str)}
    except urllib.error.HTTPError as exc:
        AI_STOPPED = True
        print(f'[WARN] Gemini HTTP {exc.code}: stop AI for this run (no paid fallback).', file=sys.stderr)
        return None
    except (TimeoutError, ValueError, KeyError, OSError, IndexError, json.JSONDecodeError) as exc:
        print('[WARN] Gemini analysis failed; no paid fallback.', file=sys.stderr)
        return None


def verify_image(item):
    """Check that the image can actually be displayed before adding it."""
    try:
        req = urllib.request.Request(item['image'], headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=25) as response:
            head = response.read(16)
            return head.startswith(b'\xff\xd8') or head.startswith(b'\x89PNG') or (head[:4] == b'RIFF' and head[8:12] == b'WEBP')
    except (OSError, ValueError):
        return False


def collect(existing, target, today):
    """A retry or manual run must not add another full daily selection."""
    today_items = [x for x in existing if x.get('date') == today]
    remaining = max(0, target - len(today_items))
    if not remaining:
        return []
    seen = {p['id'] for p in existing if p.get('id')}
    random.seed(today)
    by_category = {}
    for category, queries in SEARCHES.items():
        candidates = []
        for query in random.sample(queries, min(2, len(queries))):
            try:
                candidates += search_commons(query, category)
            except Exception as exc:
                ERRORS.append(type(exc).__name__)
                print(f'[WARN] Wikimedia query unavailable ({type(exc).__name__}).', file=sys.stderr)
            time.sleep(2)
        random.shuffle(candidates)
        by_category[category] = candidates
    chosen = []
    def take(candidate):
        if len(chosen) >= remaining or candidate['id'] in seen:
            return
        seen.add(candidate['id'])
        if verify_image(candidate):
            chosen.append(candidate)
    for category, quota in TARGET.items():
        already = sum(x.get('category') == category for x in today_items)
        for candidate in by_category[category]:
            if sum(x['category'] == category for x in chosen) >= max(0, quota - already):
                break
            take(candidate)
    extras = sum(by_category.values(), [])
    random.shuffle(extras)
    for candidate in extras:
        if len(chosen) >= remaining:
            break
        take(candidate)
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Check sources only; never write files or call Gemini')
    parser.add_argument('--max', type=int, default=8, help='Maximum total new images per Shanghai calendar day, up to 12')
    args = parser.parse_args()
    target = max(1, min(12, args.max))
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    today = now.date().isoformat()
    existing = json.loads(DATA_FILE.read_text(encoding='utf-8')) if DATA_FILE.exists() else []
    if not isinstance(existing, list):
        raise ValueError('entries.json should be a JSON array')
    chosen = collect(existing, target, today)
    for i, item in enumerate(chosen):
        print(f"[{i+1}/{len(chosen)}] {item['category']} {item['title'][:65]}")
    if args.dry_run:
        print('[INFO] Source check only. No Gemini calls, no file writes.')
        print(json.dumps(chosen[:2], ensure_ascii=False, indent=2)[:3500])
        return
    entries = chosen + existing
    analyzed = 0
    if AI_ENABLED:
        # Backfill missing cards too, so enabling AI after deployment works.
        for item in [x for x in entries if not x.get('analysis')][:8]:
            if AI_STOPPED:
                break
            result = analyze(item)
            if result and all(result.get(k) for k in ('lighting','composition','color','practice')):
                item['analysis'] = result
                analyzed += 1
            time.sleep(8)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    data_text = json.dumps(entries, ensure_ascii=False, indent=2) + '\n'
    if not DATA_FILE.exists() or DATA_FILE.read_text(encoding='utf-8') != data_text:
        DATA_FILE.write_text(data_text, encoding='utf-8')
    today_count = sum(x.get('date') == today for x in entries)
    status = {'lastAttempt': now.isoformat(), 'latestSelection': entries[0]['date'] if entries else None,
              'newItems': len(chosen), 'todayItems': today_count, 'targetItems': target,
              'analyzedItems': analyzed, 'totalItems': len(entries),
              'aiStatus': 'enabled' if AI_ENABLED else 'disabled-awaiting-free-tier-confirmation',
              'sourceErrors': len(ERRORS),
              'message': 'success' if today_count >= target else 'partial' if today_count else 'source-unavailable'}
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'[OK] Added {len(chosen)} photos; today {today_count}/{target}; analyzed {analyzed}.')

if __name__ == '__main__':
    main()
