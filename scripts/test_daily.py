"""Offline regression checks for curation limits, licensing, and AI consent."""
import datetime as dt
import importlib.util
import json
import tempfile
import unittest
import urllib.error
import io
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('daily', Path(__file__).with_name('daily.py'))
daily = importlib.util.module_from_spec(spec)
spec.loader.exec_module(daily)

class DailyTests(unittest.TestCase):
    def test_completed_day_never_fetches_again(self):
        rows = [{'id': str(n), 'date': '2026-10-20'} for n in range(8)]
        with patch.object(daily, 'search_commons', side_effect=AssertionError('unexpected network')):
            self.assertEqual(daily.collect(rows, 8, '2026-10-20'), [])

    def test_partial_day_top_up_and_dedup(self):
        def candidates(term, cat):
            return [{'id': f'{cat}-{n}', 'category': cat, 'date': '2026-10-20'} for n in range(8)]
        with patch.object(daily, 'search_commons', side_effect=candidates), patch.object(daily, 'verify_image', return_value=True), patch.object(daily.time, 'sleep'):
            old = [{'id': 'portrait-0','category':'portrait','date':'2026-10-20'}]
            chosen = daily.collect(old, 8, '2026-10-20')
            self.assertEqual(len(chosen), 7)
            self.assertEqual(len(set(x['id'] for x in chosen)), 7)
            self.assertNotIn('portrait-0', [x['id'] for x in chosen])
            self.assertEqual(sum(x['category']=='portrait' for x in chosen), 3)

    def test_dry_run_never_calls_ai_or_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'entries.json'; data.write_text('[]')
            item={'id':'example','category':'portrait','title':'Example'}
            with patch.object(daily,'DATA_FILE',data),patch.object(daily,'STATUS_FILE',Path(tmp)/'status.json'),patch.object(daily,'collect',return_value=[item]),patch.object(daily,'analyze',side_effect=AssertionError('AI forbidden')),patch('sys.argv',['daily','--dry-run']),patch.object(daily,'AI_ENABLED',True):
                daily.main()
                self.assertEqual(data.read_text(),'[]')
                self.assertFalse((Path(tmp)/'status.json').exists())

    def test_ai_disabled_without_confirmation(self):
        with patch.object(daily,'AI_ENABLED',False),patch.object(daily,'get',side_effect=AssertionError('network forbidden')):
            self.assertIsNone(daily.analyze({'image':'https://example.com/'}))

    def test_service_failure_reports_source_and_stops(self):
        failure=urllib.error.HTTPError('https://generativelanguage.googleapis.com',503,'Unavailable',{},None)
        with patch.object(daily,'AI_ENABLED',True),patch.object(daily,'AI_STOPPED',False),patch.object(daily,'AI_ERROR',None),patch.object(daily,'get',return_value=b'\xff\xd8image'),patch.object(daily.urllib.request,'urlopen',side_effect=failure),redirect_stderr(io.StringIO()):
            self.assertIsNone(daily.analyze({'image':'https://example.com/photo.jpg'}))
            self.assertTrue(daily.AI_STOPPED)
            self.assertEqual(daily.AI_ERROR,{'source':'gemini','code':503})

    def test_image_failure_is_not_reported_as_gemini(self):
        failure=urllib.error.HTTPError('https://upload.wikimedia.org',429,'Rate limit',{},None)
        with patch.object(daily,'AI_ENABLED',True),patch.object(daily,'AI_STOPPED',False),patch.object(daily,'AI_ERROR',None),patch.object(daily,'get',side_effect=failure),patch.object(daily.urllib.request,'urlopen',side_effect=AssertionError('Gemini must not be called')),redirect_stderr(io.StringIO()):
            self.assertIsNone(daily.analyze({'image':'https://example.com/photo.jpg'}))
            self.assertEqual(daily.AI_ERROR,{'source':'image','code':429})

    def test_licenses(self):
        def info(license):return {'extmetadata':{'LicenseShortName':{'value':license}}}
        for license in ('CC BY-SA 4.0','CC BY 4.0','CC0','Public domain'):
            self.assertTrue(daily.licensed(info(license)))
        for license in ('CC BY-NC 4.0','CC BY-ND 4.0','All rights reserved',''):
            self.assertFalse(daily.licensed(info(license)))

if __name__=='__main__':unittest.main()
