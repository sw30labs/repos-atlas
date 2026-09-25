"""Release regressions: privacy boundaries, generic data, and the full local pipeline."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from unittest import mock
import urllib.error
import urllib.request

import atlas
import review
import survey


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def render(data):
    return ''.join(atlas.build_rest(*atlas.build(data)))


class TestLocalDomains(unittest.TestCase):
    def test_default_and_custom_groups(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, 'domains.json')
            self.assertEqual(atlas.load_domains(path), [('Meta & Tooling', [])])
            path.write_text('{"Apps": ["sample"]}', encoding='utf-8')
            self.assertEqual(atlas.load_domains(path), [('Apps', ['sample']), ('Meta & Tooling', [])])

    def test_invalid_and_duplicate_groups_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td, 'domains.json')
            for bad in ([], {'Apps': 'sample'}, {'Apps': [5]}, {'': []},
                        {'Apps': ['same'], 'Tools': ['same']}):
                with self.subTest(bad=bad):
                    path.write_text(json.dumps(bad), encoding='utf-8')
                    with self.assertRaises(ValueError):
                        atlas.load_domains(path)


class TestLocalTransport(unittest.TestCase):
    def test_loopback_urls(self):
        self.assertEqual(review.local_url('http://localhost:8000/v1'), 'http://127.0.0.1:8000/v1')
        for url in ('http://127.0.0.1:54321/v1', 'https://[::1]:8000/v1'):
            self.assertEqual(review.local_url(url), url)

    def test_remote_or_ambiguous_endpoints_are_rejected_before_io(self):
        with mock.patch.object(review, 'local_open') as opened:
            for url in ('https://example.com/v1', 'http://192.168.1.2/v1',
                        'http://0.0.0.0/v1', 'file:///tmp/model',
                        'http://localhost.example.com/v1', 'http://127.1/v1',
                        'http://user:pass@localhost/v1', 'http://localhost/v1?key=example',
                        'http://localhost/v1#fragment', 'http://localhost:bad/v1'):
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        review._post(url, {'private': 'fictional'}, 1)
                    with self.assertRaises(ValueError):
                        review._get(url)
            opened.assert_not_called()

    def test_system_proxies_are_disabled(self):
        with mock.patch.dict(os.environ, {'HTTP_PROXY': 'http://example.com:8080'}), \
                mock.patch.object(review.urllib.request, 'build_opener') as build:
            review.local_open('http://127.0.0.1/v1', 1)
            proxy, redirect = build.call_args.args
            self.assertIsInstance(proxy, urllib.request.ProxyHandler)
            self.assertEqual(proxy.proxies, {})
            self.assertIsInstance(redirect, review.NoRedirect)

    def test_redirects_are_refused(self):
        req = urllib.request.Request('http://127.0.0.1/v1')
        with self.assertRaises(urllib.error.URLError):
            review.NoRedirect().redirect_request(req, None, 302, 'Found', {}, 'https://example.com')


class TestPrivacy(unittest.TestCase):
    def test_remote_credentials_and_query_are_removed(self):
        self.assertEqual(survey.redact_origin('https://demo:fake-password@example.com/owner/repo.git?key=demo#private'),
                         'https://example.com/owner/repo.git')
        self.assertEqual(survey.redact_origin('ssh://user@example.com:2222/repo.git'),
                         'ssh://example.com:2222/repo.git')
        self.assertEqual(survey.redact_origin('git@example.com:owner/repo.git'),
                         'git@example.com:owner/repo.git')
        self.assertEqual(survey.redact_origin('http://localhost:bad/repo'), '[invalid remote URL]')

    def test_evidence_reads_the_surveyed_root(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td, 'sample')
            repo.mkdir()
            (repo / 'README.md').write_text('Evidence from the selected folder.', encoding='utf-8')
            text = review.evidence({'name': 'sample'}, root=td)
            self.assertIn('Evidence from the selected folder.', text)

    def test_review_main_passes_the_saved_root(self):
        data = {'root': '/example/projects', 'repos': [{'name': 'sample'}]}
        with mock.patch.object(review, 'load', side_effect=[data, {}]), \
                mock.patch.object(review, 'resolve_model', return_value='demo'), \
                mock.patch.object(review, 'evidence', return_value='') as evidence, \
                mock.patch('sys.argv', ['review.py', '--no-synthesis']), \
                contextlib.redirect_stdout(io.StringIO()):
            review.main()
        evidence.assert_called_once_with({'name': 'sample'}, root='/example/projects')

    def test_evidence_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ('../outside', '..', '.', '/absolute'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    review.evidence({'name': name}, root=td)


class TestRenderer(unittest.TestCase):
    def test_empty_inventory(self):
        with mock.patch.object(atlas, 'REVIEW', {}):
            page = render({'generated': '2026-09-25T12:00:00', 'repos': []})
        self.assertIn('No commit history found', page)
        self.assertIn('0 shown', page)

    def test_tooltip_text_stays_text_after_attribute_decoding(self):
        attack = '<img src=x onerror="alert(1)"> & text'
        with tempfile.TemporaryDirectory() as td, mock.patch.object(atlas, 'HERE', td), \
                mock.patch.object(atlas, 'REVIEW', {}):
            fixture = {'generated': '2026-09-25', 'repos': [{
                'name': attack, 'blurb': attack, 'is_git': False, 'files': 1,
                'bytes': 20, 'loc': {attack: 10}}]}
            Path(td, 'survey.json').write_text(json.dumps(fixture), encoding='utf-8')
            page = render(atlas.load())
        parsed = Elements(page)
        tips = [attrs['data-tip'] for _, attrs in parsed.elements if 'data-tip' in attrs]
        self.assertTrue(tips)
        for tip in tips:
            self.assertFalse(any(tag == 'img' for tag, _ in Elements(tip).elements))
        self.assertIn('&lt;img', tips[-1])

    def test_demo_ignores_private_review_and_has_matching_table_columns(self):
        demo = Path(atlas.__file__).parent / 'examples' / 'survey.demo.json'
        with mock.patch.object(atlas, 'REVIEW', {'briefs': {'private': {'one_liner': 'private'}}}):
            data = atlas.load(demo, include_review=False)
            self.assertEqual(atlas.REVIEW, {})
            page = render(data)
        self.assertNotIn('private', page)
        parsed = Elements(page)
        headers = sum(tag == 'th' for tag, _ in parsed.elements)
        cells = sum(tag == 'td' for tag, _ in parsed.elements)
        self.assertEqual(headers, 14)
        self.assertEqual(cells, headers * len(data['repos']))


class TestSurveyIntegration(unittest.TestCase):
    def test_temp_git_repo_to_html_without_index_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td, 'projects')
            root.mkdir()
            repo = root / 'sample'
            repo.mkdir()
            out = Path(td, 'output')
            out.mkdir()

            def git(*args, date=None):
                env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
                if date:
                    env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
                return subprocess.run(['git', '-c', 'user.name=Demo Contributor',
                                       '-c', 'user.email=demo@example.com', '-c', 'commit.gpgsign=false',
                                       '-c', 'core.hooksPath=' + str(Path(td, 'no-hooks')), *args],
                                      cwd=repo, env=env, check=True, capture_output=True, text=True)

            git('init')
            (repo / 'README.md').write_text('# Example\nA fictional project.\n', encoding='utf-8')
            git('add', 'README.md')
            git('commit', '-m', 'First sample', date='2020-01-01T12:00:00+00:00')
            (repo / 'app.py').write_text('print("sample")\n', encoding='utf-8')
            git('add', 'app.py')
            git('commit', '-m', 'Second sample', date='2026-01-01T12:00:00+00:00')
            git('remote', 'add', 'origin', 'https://demo:fake-password@example.com/demo/sample.git?key=demo')
            (repo / 'app.py').write_text('print("changed")\n', encoding='utf-8')
            before = (repo / '.git' / 'index').read_bytes()
            with mock.patch.object(survey, 'HERE', str(out)), contextlib.redirect_stdout(io.StringIO()):
                survey.survey(str(root), quiet=True)
            data = json.loads((out / 'survey.json').read_text())
            rec = data['repos'][0]
            self.assertEqual(rec['commits'], 2)
            self.assertTrue(rec['born'].startswith('2020-01-01'))
            self.assertTrue(rec['last'].startswith('2026-01-01'))
            self.assertEqual(rec['dirty'], 1)
            self.assertEqual(rec['origin'], 'https://example.com/demo/sample.git')
            self.assertEqual((repo / '.git' / 'index').read_bytes(), before)
            self.assertFalse((repo / '.git' / 'index.lock').exists())
            with mock.patch.object(atlas, 'HERE', str(out)), mock.patch.object(atlas, 'REVIEW', {}):
                page = render(atlas.load())
            self.assertIn('sample', page)
            self.assertIn('1 uncommitted', page)
            self.assertNotIn('fake-password', page)


if __name__ == '__main__':
    unittest.main()
