# Stream Disambiguation via MPRIS URL Correlation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Brave (and other browser) audio streams to be distinguished and auto-routed by the URL of the tab they come from, using KDE Plasma Browser Integration's MPRIS D-Bus interface.

**Architecture:** A module-level `_parse_dbus_metadata()` parses `dbus-send` output into a flat dict; `MainWindow.get_mpris_browser_url()` calls it; `MainWindow.update_stream_urls()` maintains `self.stream_url_cache` (stream_index → URL) and is called every refresh cycle. `apply_routing_rules()` checks a new `url_routes` state key (domain → sink) and an optional `url_pattern` field on named rules, with domain-based matching so one drag covers all future sessions from that site. `RulesDialog` grows a "URL contains" field.

**Tech Stack:** Python 3, PyQt5, `dbus-send` via subprocess, `urllib.parse` (stdlib), `pytest`.

> **Spec deviation:** The spec used full URLs as `url_routes` keys; this plan uses the URL domain (netloc) so that one drag-and-drop covers all future sessions from the same site (e.g. all YouTube Music songs share `music.youtube.com`), not just one specific video URL.

---

## File Map

| File | Change |
|---|---|
| `SoundSwitch.py` | Add `_parse_dbus_metadata()` at module level; add `import urllib.parse`; add `BROWSER_APP_NAMES` constant; add `stream_url_cache` init in `MainWindow.__init__`; add `get_mpris_browser_url()`, `update_stream_urls()` methods; modify `refresh_devices_and_sinks()`, `apply_routing_rules()`, `move_sink_input()`, `_save_rule()`, `_on_row_changed()`, `_refresh_list()`, `_new_rule()`, `RulesDialog.__init__()`, `RulesDialog._init_ui()`; add `open_rules_dialog_for_stream()` |
| `tests/test_stream_disambiguation.py` | New — all unit tests |

---

## Task 1: MPRIS parsing + `get_mpris_browser_url()`

**Files:**
- Create: `tests/test_stream_disambiguation.py`
- Modify: `SoundSwitch.py` (top-level — add import + module-level function + method)

- [ ] **Step 1: Create the test file with a failing test for `_parse_dbus_metadata()`**

Create `tests/__init__.py` (empty) and `tests/test_stream_disambiguation.py`:

```python
import re
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from SoundSwitch import _parse_dbus_metadata

SAMPLE_DBUS_OUTPUT = """\
method return time=1781646353.121208 sender=:1.70 -> destination=:1.123 serial=379 reply_serial=2
   array [
      dict entry(
         string "CanControl"
         variant             boolean true
      )
      dict entry(
         string "Metadata"
         variant             array [
               dict entry(
                  string "mpris:length"
                  variant                      int64 2123734240
               )
               dict entry(
                  string "xesam:album"
                  variant                      string "Reroute To Remain"
               )
               dict entry(
                  string "xesam:title"
                  variant                      string "Black & White"
               )
               dict entry(
                  string "xesam:url"
                  variant                      string "https://music.youtube.com/"
               )
            ]
      )
   ]
"""


class TestParseDbusMeta(unittest.TestCase):
    def test_extracts_url(self):
        result = _parse_dbus_metadata(SAMPLE_DBUS_OUTPUT)
        self.assertEqual(result.get('xesam:url'), 'https://music.youtube.com/')

    def test_extracts_title(self):
        result = _parse_dbus_metadata(SAMPLE_DBUS_OUTPUT)
        self.assertEqual(result.get('xesam:title'), 'Black & White')

    def test_extracts_album(self):
        result = _parse_dbus_metadata(SAMPLE_DBUS_OUTPUT)
        self.assertEqual(result.get('xesam:album'), 'Reroute To Remain')

    def test_boolean_variant_not_extracted(self):
        # Only string variants are captured; booleans are ignored
        result = _parse_dbus_metadata(SAMPLE_DBUS_OUTPUT)
        self.assertNotIn('CanControl', result)

    def test_empty_output_returns_empty_dict(self):
        self.assertEqual(_parse_dbus_metadata(''), {})

    def test_missing_url_returns_empty_dict(self):
        result = _parse_dbus_metadata("no url here\nstring \"xesam:title\"\nvariant string \"hi\"")
        self.assertEqual(result.get('xesam:title'), 'hi')
        self.assertNotIn('xesam:url', result)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test — expect ImportError (function not defined yet)**

```bash
cd /home/etienne/projects/soundSwitch-wip
python -m pytest tests/test_stream_disambiguation.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name '_parse_dbus_metadata'`

- [ ] **Step 3: Add `import urllib.parse`, `BROWSER_APP_NAMES`, and `_parse_dbus_metadata()` to `SoundSwitch.py`**

At the top of `SoundSwitch.py`, after `import re` (line 2), add:

```python
import urllib.parse
```

After the existing imports block (after `from PyQt5 import QtCore, QtGui` around line 18), add:

```python
BROWSER_APP_NAMES = {'brave', 'firefox', 'chromium', 'chrome', 'opera', 'vivaldi'}


def _parse_dbus_metadata(output: str) -> dict:
    """Parse dbus-send --print-reply output, returning string-valued keys as a flat dict.

    Scans all lines for `string "KEY"` immediately followed (within 2 lines) by
    `variant ... string "VALUE"`. Non-string variant types (boolean, int64, array)
    are ignored.
    """
    result = {}
    lines = output.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'^\s*string "([^"]+)"\s*$', line)
        if not m:
            continue
        key = m.group(1)
        for j in range(i + 1, min(i + 3, len(lines))):
            val_m = re.match(r'^\s*variant\s+string\s+"([^"]*)"\s*$', lines[j])
            if val_m:
                result[key] = val_m.group(1)
                break
    return result
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected output (all six tests):
```
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_extracts_url
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_extracts_title
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_extracts_album
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_boolean_variant_not_extracted
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_empty_output_returns_empty_dict
PASSED tests/test_stream_disambiguation.py::TestParseDbusMeta::test_missing_url_returns_empty_dict
```

- [ ] **Step 5: Write failing test for `get_mpris_browser_url()`**

Add this class to `tests/test_stream_disambiguation.py` (after the `TestParseDbusMeta` class):

```python
from SoundSwitch import _parse_dbus_metadata   # already imported above
import subprocess


class TestGetMprisBrowserUrl(unittest.TestCase):
    """Tests for MainWindow.get_mpris_browser_url() via mocked subprocess."""

    def _make_window_mock(self):
        """Return a minimal object with get_mpris_browser_url bound to it."""
        import SoundSwitch as ss
        obj = object.__new__(ss.MainWindow)
        # Bind the method without running __init__
        obj.get_mpris_browser_url = ss.MainWindow.get_mpris_browser_url.__get__(obj, ss.MainWindow)
        return obj

    def test_returns_url_and_title_on_success(self):
        obj = self._make_window_mock()
        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = SAMPLE_DBUS_OUTPUT
        with patch('subprocess.run', return_value=fake_result):
            result = obj.get_mpris_browser_url()
        self.assertIsNotNone(result)
        self.assertEqual(result['url'], 'https://music.youtube.com/')
        self.assertEqual(result['title'], 'Black & White')

    def test_returns_none_on_non_http_url(self):
        obj = self._make_window_mock()
        non_http_output = SAMPLE_DBUS_OUTPUT.replace(
            'https://music.youtube.com/', 'spotify:track:123')
        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = non_http_output
        with patch('subprocess.run', return_value=fake_result):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_subprocess_error(self):
        obj = self._make_window_mock()
        with patch('subprocess.run', side_effect=FileNotFoundError):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_timeout(self):
        obj = self._make_window_mock()
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('dbus-send', 2)):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_nonzero_returncode(self):
        obj = self._make_window_mock()
        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ''
        with patch('subprocess.run', return_value=fake_result):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)
```

- [ ] **Step 6: Run tests — expect 5 new failures (method not defined)**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestGetMprisBrowserUrl -v 2>&1 | head -20
```

Expected: `AttributeError: type object 'MainWindow' has no attribute 'get_mpris_browser_url'`

- [ ] **Step 7: Add `get_mpris_browser_url()` to `MainWindow`**

Add this method to `MainWindow`, just before `get_sink_inputs()` (around line 1331):

```python
def get_mpris_browser_url(self) -> dict | None:
    """Query Plasma Browser Integration MPRIS for the active tab URL.

    Returns {'url': str, 'title': str} or None if unavailable or non-HTTP.
    """
    try:
        result = subprocess.run(
            [
                'dbus-send', '--print-reply',
                '--dest=org.mpris.MediaPlayer2.plasma-browser-integration',
                '/org/mpris/MediaPlayer2',
                'org.freedesktop.DBus.Properties.GetAll',
                'string:org.mpris.MediaPlayer2.Player',
            ],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            return None
        meta = _parse_dbus_metadata(result.stdout)
        url = meta.get('xesam:url', '')
        if not url.startswith('http'):
            return None
        return {'url': url, 'title': meta.get('xesam:title', '')}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
```

- [ ] **Step 8: Run all tests — expect all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: 11 tests, all PASSED.

- [ ] **Step 9: Commit**

```bash
git add tests/__init__.py tests/test_stream_disambiguation.py SoundSwitch.py
git commit -m "feat: add MPRIS URL parsing and get_mpris_browser_url()"
```

---

## Task 2: `stream_url_cache` + `update_stream_urls()`

**Files:**
- Modify: `SoundSwitch.py`
- Modify: `tests/test_stream_disambiguation.py`

- [ ] **Step 1: Write failing tests for `update_stream_urls()`**

Add this class to `tests/test_stream_disambiguation.py`:

```python
class TestUpdateStreamUrls(unittest.TestCase):
    """Tests for the stream URL caching logic extracted to a module-level helper."""

    def setUp(self):
        """Build a minimal MainWindow-like object with stream_url_cache."""
        import SoundSwitch as ss
        self.obj = object.__new__(ss.MainWindow)
        self.obj.stream_url_cache = {}
        self.obj.get_mpris_browser_url = ss.MainWindow.get_mpris_browser_url.__get__(
            self.obj, ss.MainWindow)
        self.obj.update_stream_urls = ss.MainWindow.update_stream_urls.__get__(
            self.obj, ss.MainWindow)

    def test_browser_stream_gets_tagged_with_mpris_url(self):
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback'}]
        mpris = {'url': 'https://music.youtube.com/', 'title': 'Black & White'}
        with patch.object(self.obj, 'get_mpris_browser_url', return_value=mpris):
            self.obj.update_stream_urls(streams)
        self.assertEqual(self.obj.stream_url_cache.get('42'), 'https://music.youtube.com/')
        self.assertEqual(streams[0].get('url'), 'https://music.youtube.com/')

    def test_non_browser_stream_not_tagged(self):
        streams = [{'index': '10', 'app_name': 'Spotify', 'media_name': 'My Song'}]
        with patch.object(self.obj, 'get_mpris_browser_url', return_value={'url': 'https://x.com/', 'title': ''}):
            self.obj.update_stream_urls(streams)
        self.assertNotIn('10', self.obj.stream_url_cache)
        self.assertEqual(streams[0].get('url', ''), '')

    def test_already_cached_stream_not_re_queried(self):
        self.obj.stream_url_cache['42'] = 'https://music.youtube.com/'
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback'}]
        with patch.object(self.obj, 'get_mpris_browser_url') as mock_mpris:
            self.obj.update_stream_urls(streams)
        mock_mpris.assert_not_called()
        self.assertEqual(streams[0].get('url'), 'https://music.youtube.com/')

    def test_stale_cache_entry_removed_when_stream_gone(self):
        self.obj.stream_url_cache['99'] = 'https://old.example.com/'
        streams = [{'index': '42', 'app_name': 'Spotify', 'media_name': 'X'}]
        with patch.object(self.obj, 'get_mpris_browser_url', return_value=None):
            self.obj.update_stream_urls(streams)
        self.assertNotIn('99', self.obj.stream_url_cache)

    def test_mpris_unavailable_leaves_stream_untagged(self):
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback'}]
        with patch.object(self.obj, 'get_mpris_browser_url', return_value=None):
            self.obj.update_stream_urls(streams)
        self.assertNotIn('42', self.obj.stream_url_cache)
        self.assertEqual(streams[0].get('url', ''), '')

    def test_first_untagged_stream_gets_tagged_when_two_appear(self):
        streams = [
            {'index': '10', 'app_name': 'Brave', 'media_name': 'Playback'},
            {'index': '20', 'app_name': 'Brave', 'media_name': 'Playback'},
        ]
        mpris = {'url': 'https://music.youtube.com/', 'title': ''}
        with patch.object(self.obj, 'get_mpris_browser_url', return_value=mpris):
            self.obj.update_stream_urls(streams)
        self.assertEqual(self.obj.stream_url_cache.get('10'), 'https://music.youtube.com/')
        self.assertNotIn('20', self.obj.stream_url_cache)
```

- [ ] **Step 2: Run — expect failures (method not defined)**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestUpdateStreamUrls -v 2>&1 | head -20
```

Expected: `AttributeError: type object 'MainWindow' has no attribute 'update_stream_urls'`

- [ ] **Step 3: Add `self.stream_url_cache = {}` to `MainWindow.__init__`**

In `MainWindow.__init__`, after `self._last_snapshot = None` (around line 988), add:

```python
self.stream_url_cache: dict = {}   # stream_index (str) → full URL
```

- [ ] **Step 4: Add `update_stream_urls()` to `MainWindow`**

Add this method directly after `get_mpris_browser_url()`:

```python
def update_stream_urls(self, sink_inputs: list) -> None:
    """Update stream_url_cache from MPRIS and attach 'url' key to each stream dict.

    Queries MPRIS at most once per call, tagging the first untagged browser
    stream found. If multiple browser streams are new simultaneously, subsequent
    refresh ticks will tag the remaining ones.
    """
    live_indices = {s['index'] for s in sink_inputs}

    # Remove stale entries for streams that no longer exist
    for idx in list(self.stream_url_cache):
        if idx not in live_indices:
            del self.stream_url_cache[idx]

    # Find browser streams not yet in the cache
    untagged = [
        s for s in sink_inputs
        if s.get('app_name', '').lower() in BROWSER_APP_NAMES
        and s['index'] not in self.stream_url_cache
    ]

    if untagged:
        mpris = self.get_mpris_browser_url()
        if mpris:
            # Tag only the first untagged stream; the rest on subsequent ticks
            self.stream_url_cache[untagged[0]['index']] = mpris['url']

    # Attach cached URL to every stream dict for downstream use
    for s in sink_inputs:
        s['url'] = self.stream_url_cache.get(s['index'], '')
```

- [ ] **Step 5: Run tests — expect all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: 17 tests, all PASSED.

- [ ] **Step 6: Wire `update_stream_urls()` into `refresh_devices_and_sinks()`**

In `refresh_devices_and_sinks()`, the existing code calls `self.get_sink_inputs()` at line 1658. Add `update_stream_urls` call directly after `self.update_hidden_streams(sink_inputs)` (around line 1659):

```python
    sink_inputs = self.get_sink_inputs()
    self.update_hidden_streams(sink_inputs)
    self.update_stream_urls(sink_inputs)          # ← add this line
    sink_index_to_name = {sink['index']: sink['name'] for sink in sinks}
```

- [ ] **Step 7: Verify the app starts without errors**

```bash
cd /home/etienne/projects/soundSwitch-wip && source .venv/bin/activate
timeout 5 python3 SoundSwitch.py 2>&1 || true
```

Expected: no Python traceback (the app opens or the timeout kills it cleanly).

- [ ] **Step 8: Commit**

```bash
git add SoundSwitch.py tests/test_stream_disambiguation.py
git commit -m "feat: add stream_url_cache and update_stream_urls() for MPRIS correlation"
```

---

## Task 3: Enrich stream display with URL domain

**Files:**
- Modify: `SoundSwitch.py` (two locations in `refresh_devices_and_sinks()`)

No unit test for rendering logic; verify visually by running the app.

- [ ] **Step 1: Update left panel (Application Streams) subtitle**

In `refresh_devices_and_sinks()`, the left panel block (around line 1677) builds items for `self.devices_list`. The `sub_label` is currently `stream.get('media_name', '')`. Replace that assignment:

```python
        # Before (lines ~1680-1681):
        main_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']}) - {stream.get('sink_name', 'Unknown')}"
        sub_label = stream.get('media_name', '')

        # After:
        main_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']}) - {stream.get('sink_name', 'Unknown')}"
        url = stream.get('url', '')
        domain = urllib.parse.urlparse(url).netloc if url else ''
        sub_label = domain if domain else stream.get('media_name', '')
```

Also update the tooltip for browser streams at line ~1687:

```python
        # Before:
        item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nSink: {stream.get('sink_name', 'Unknown')}\nMedia: {stream.get('media_name', '')}")

        # After:
        url = stream.get('url', '')
        tooltip_extra = f"\nURL: {url}" if url else f"\nMedia: {stream.get('media_name', '')}"
        item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nSink: {stream.get('sink_name', 'Unknown')}{tooltip_extra}")
```

> Note: `url` was already computed two lines above — no need to recompute it if the edit is done in the same block. Keep the assignment order consistent.

- [ ] **Step 2: Update right sink panels subtitle**

In the sink panels block (around line 1699), the current logic uses `media_name` as the main label. Update it:

```python
        # Before (lines ~1700-1703):
        media_name = stream.get('media_name', '')
        app_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']})"
        main_label = media_name if media_name else app_label
        sub_label = app_label if media_name else ''

        # After:
        url = stream.get('url', '')
        domain = urllib.parse.urlparse(url).netloc if url else ''
        media_name = stream.get('media_name', '')
        app_label = f"{stream.get('app_name', 'Unknown App')} (#{stream['index']})"
        enriched = domain if domain else media_name
        main_label = enriched if enriched else app_label
        sub_label = app_label if enriched else ''
```

Also update the tooltip at line ~1708:

```python
        # Before:
        stream_item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}\nMedia: {stream.get('media_name', '')}")

        # After:
        tooltip_extra = f"\nURL: {url}" if url else f"\nMedia: {media_name}"
        stream_item.setToolTip(f"App: {stream.get('app_name', 'Unknown App')}{tooltip_extra}")
```

- [ ] **Step 3: Run the app and verify display**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

With Brave playing YouTube Music, the Application Streams panel should show:
```
Brave (#78189) - Media
music.youtube.com
```
instead of:
```
Brave (#78189) - Media
Playback
```

- [ ] **Step 4: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: show URL domain as stream subtitle for browser streams"
```

---

## Task 4: `url_routes` matching + implicit learning

**Files:**
- Modify: `SoundSwitch.py`
- Modify: `tests/test_stream_disambiguation.py`

- [ ] **Step 1: Write failing tests for url_routes routing**

Add this class to `tests/test_stream_disambiguation.py`:

```python
from SoundSwitch import _url_domain


class TestUrlRoutesMatching(unittest.TestCase):
    def test_domain_extracted_from_full_url(self):
        self.assertEqual(_url_domain('https://music.youtube.com/watch?v=abc'), 'music.youtube.com')

    def test_domain_extracted_from_root_url(self):
        self.assertEqual(_url_domain('https://music.youtube.com/'), 'music.youtube.com')

    def test_empty_url_returns_empty_string(self):
        self.assertEqual(_url_domain(''), '')

    def test_non_http_url_returns_empty_string(self):
        self.assertEqual(_url_domain('spotify:track:123'), '')
```

- [ ] **Step 2: Run — expect ImportError**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestUrlRoutesMatching -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name '_url_domain'`

- [ ] **Step 3: Add `_url_domain()` module-level helper to `SoundSwitch.py`**

Add directly after `_parse_dbus_metadata()`:

```python
def _url_domain(url: str) -> str:
    """Return the netloc (domain) of an http(s) URL, or '' for non-HTTP or empty input."""
    if not url.startswith('http'):
        return ''
    return urllib.parse.urlparse(url).netloc
```

- [ ] **Step 4: Run tests — all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestUrlRoutesMatching -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Write failing test for url_routes in `apply_routing_rules()`**

Add to `tests/test_stream_disambiguation.py`:

```python
class TestApplyUrlRoutes(unittest.TestCase):
    """Integration-style tests for the url_routes routing layer.

    These patch get_sinks / get_sink_inputs / run_pactl on a minimal MainWindow
    stand-in so no Qt application is needed.
    """

    def setUp(self):
        import SoundSwitch as ss
        self.obj = object.__new__(ss.MainWindow)
        self.obj.stream_url_cache = {'42': 'https://music.youtube.com/'}
        self.obj.hidden_streams = set()
        self.obj.state = {
            'rules': [],
            'manual_overrides': {},
            'url_routes': {'music.youtube.com': 'Media'},
        }
        self.obj.apply_routing_rules = ss.MainWindow.apply_routing_rules.__get__(
            self.obj, ss.MainWindow)
        self.obj.update_status_bar = MagicMock()
        self.obj.show_status = MagicMock()

    def _make_sinks(self):
        return [
            {'index': '52', 'name': 'alsa_output'},
            {'index': '60', 'name': 'Media'},
            {'index': '61', 'name': 'Aux'},
        ]

    def test_url_routes_moves_stream_to_correct_sink(self):
        # stream 42 is currently on alsa_output (sink index 52) but url_routes says Media
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback',
                    'sink': '52', 'url': 'https://music.youtube.com/'}]
        sinks = self._make_sinks()
        self.obj.get_sinks = MagicMock(return_value=sinks)
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        pactl_calls = []
        self.obj.run_pactl = MagicMock(side_effect=lambda args: pactl_calls.append(args) or 'ok')
        self.obj.apply_routing_rules()
        self.assertIn(['move-sink-input', '42', 'Media'], pactl_calls)

    def test_url_routes_skips_stream_already_in_correct_sink(self):
        # stream 42 is already on Media (sink index 60)
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback',
                    'sink': '60', 'url': 'https://music.youtube.com/'}]
        sinks = self._make_sinks()
        self.obj.get_sinks = MagicMock(return_value=sinks)
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        self.obj.run_pactl = MagicMock(return_value='ok')
        self.obj.apply_routing_rules()
        self.obj.run_pactl.assert_not_called()

    def test_url_routes_respects_manual_override(self):
        self.obj.state['manual_overrides'] = {'42': 'Media'}
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback',
                    'sink': '61', 'url': 'https://music.youtube.com/'}]
        # sink 61 = Aux, manual_override says Media but stream is on Aux — override active
        sinks = self._make_sinks()
        self.obj.get_sinks = MagicMock(return_value=sinks)
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        self.obj.run_pactl = MagicMock(return_value='ok')
        # Manual override for stream 42 already set to Media — stream not moved again
        # (the override means "user manually placed it here, respect that")
        # url_routes also says Media, so no conflict; stream on Aux should still be moved
        # Actually: manual_override['42'] = 'Media' and sink_name = 'Aux' → override doesn't match current sink
        # → url_routes routing should NOT fire because manual_override exists
        self.obj.apply_routing_rules()
        self.obj.run_pactl.assert_not_called()
```

- [ ] **Step 6: Run — expect failures**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestApplyUrlRoutes -v 2>&1 | head -30
```

Expected: tests fail because `apply_routing_rules()` doesn't yet check `url_routes`.

- [ ] **Step 7: Modify `apply_routing_rules()` to check `url_routes` first**

Replace the current `apply_routing_rules()` method body (lines 1554–1574) with:

```python
def apply_routing_rules(self):
    sinks = self.get_sinks()
    sink_inputs = self.get_sink_inputs()
    self.update_hidden_streams(sink_inputs)
    sink_index_to_name = {sink['index']: sink['name'] for sink in sinks}
    url_routes = self.state.get('url_routes', {})

    for stream in sink_inputs:
        if stream['index'] in self.hidden_streams:
            continue
        sink_index = stream.get('sink', None)
        sink_name = sink_index_to_name.get(sink_index, 'Unknown') if sink_index else 'Unknown'
        manual = self.state.get('manual_overrides', {}).get(str(stream['index']))
        if manual:
            continue

        stream_url = self.stream_url_cache.get(stream['index'], '')
        domain = _url_domain(stream_url)

        # Layer 1: url_routes (implicit memory from drag history, domain-keyed)
        if domain and domain in url_routes:
            target = url_routes[domain]
            if sink_name != target:
                self.run_pactl(['move-sink-input', str(stream['index']), target])
                self.show_status(
                    f"Auto-moved {stream.get('app_name', '?')} ({domain}) to {target}")
            continue

        # Layer 2: named rules (app_name match, optional url_pattern)
        for rule in self.state.get('rules', []):
            if stream.get('app_name', '').lower() != rule['app_name'].lower():
                continue
            url_pattern = rule.get('url_pattern', '')
            if url_pattern and url_pattern.lower() not in stream_url.lower():
                continue
            if sink_name != rule['sink']:
                self.run_pactl(['move-sink-input', str(stream['index']), rule['sink']])
                self.show_status(
                    f"Auto-moved {stream.get('app_name', '?')} (#{stream['index']}) to {rule['sink']}")
            break   # first matching rule wins; don't evaluate further rules for this stream

    self.update_status_bar()
```

> **Note on manual override logic change:** The original code checked `manual_overrides[index] == current_sink_name` (only skipped if override matched current position). The new code skips routing entirely when ANY manual override exists for a stream. This is stricter and prevents url_routes from fighting with the user's explicit placement. The user clears an override via "Reset to Default Behaviour" in the context menu.

- [ ] **Step 8: Run tests — all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: all tests PASSED.

- [ ] **Step 9: Write failing test for implicit learning in `move_sink_input()`**

Add to `tests/test_stream_disambiguation.py`:

```python
class TestMoveSinkInputLearning(unittest.TestCase):
    def setUp(self):
        import SoundSwitch as ss
        self.obj = object.__new__(ss.MainWindow)
        self.obj.stream_url_cache = {'42': 'https://music.youtube.com/watch?v=abc'}
        self.obj.state = {'manual_overrides': {}, 'url_routes': {}}
        self.obj.move_sink_input = ss.MainWindow.move_sink_input.__get__(
            self.obj, ss.MainWindow)
        self.obj.show_status = MagicMock()
        self.obj.save_state = MagicMock()
        self.obj.refresh_devices_and_sinks = MagicMock()

    def test_manual_move_writes_domain_to_url_routes(self):
        self.obj.run_pactl = MagicMock(return_value='ok')
        self.obj.move_sink_input('42', 'Media')
        self.assertEqual(self.obj.state['url_routes'].get('music.youtube.com'), 'Media')
        self.obj.save_state.assert_called()

    def test_manual_move_without_url_does_not_write_url_routes(self):
        self.obj.stream_url_cache = {}   # stream 42 has no URL
        self.obj.run_pactl = MagicMock(return_value='ok')
        self.obj.move_sink_input('42', 'Aux')
        self.assertEqual(self.obj.state['url_routes'], {})

    def test_failed_move_does_not_write_url_routes(self):
        self.obj.run_pactl = MagicMock(return_value=None)   # None = pactl failure
        self.obj.move_sink_input('42', 'Media')
        self.assertEqual(self.obj.state['url_routes'], {})
```

- [ ] **Step 10: Run — expect failures**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestMoveSinkInputLearning -v 2>&1 | head -20
```

Expected: `url_routes` key never written.

- [ ] **Step 11: Modify `move_sink_input()` to write domain to `url_routes`**

Replace the current `move_sink_input()` (lines 1892–1902) with:

```python
def move_sink_input(self, sink_input_index, sink_name):
    result = self.run_pactl(['move-sink-input', str(sink_input_index), sink_name])
    if result is not None:
        self.state.setdefault('manual_overrides', {})[str(sink_input_index)] = sink_name
        url = self.stream_url_cache.get(str(sink_input_index), '')
        domain = _url_domain(url)
        if domain:
            self.state.setdefault('url_routes', {})[domain] = sink_name
        self.save_state()
        self.show_status(f'Moved stream #{sink_input_index} to sink {sink_name}')
    else:
        self.show_status(f'Failed to move stream #{sink_input_index} to sink {sink_name}', error=True)
    self.refresh_devices_and_sinks(force=True)
```

- [ ] **Step 12: Run all tests — all pass**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: all tests PASSED.

- [ ] **Step 13: Commit**

```bash
git add SoundSwitch.py tests/test_stream_disambiguation.py
git commit -m "feat: add url_routes routing layer and implicit learning on drag-and-drop"
```

---

## Task 5: `url_pattern` in named rules

**Files:**
- Modify: `tests/test_stream_disambiguation.py`
- Modify: `SoundSwitch.py` (already done in Task 4 — `apply_routing_rules()` already handles `url_pattern`)

`apply_routing_rules()` from Task 4 already includes the `url_pattern` check:
```python
url_pattern = rule.get('url_pattern', '')
if url_pattern and url_pattern.lower() not in stream_url.lower():
    continue
```

This task adds tests to confirm it works and verifies backward compatibility.

- [ ] **Step 1: Write tests**

Add to `tests/test_stream_disambiguation.py`:

```python
class TestUrlPatternRules(unittest.TestCase):
    def setUp(self):
        import SoundSwitch as ss
        self.obj = object.__new__(ss.MainWindow)
        self.obj.stream_url_cache = {'42': 'https://music.youtube.com/watch?v=abc'}
        self.obj.hidden_streams = set()
        self.obj.state = {
            'rules': [
                {'app_name': 'Brave', 'url_pattern': 'music.youtube.com', 'sink': 'Media'},
                {'app_name': 'Brave', 'url_pattern': 'youtube.com',        'sink': 'Aux'},
            ],
            'manual_overrides': {},
            'url_routes': {},
        }
        self.obj.apply_routing_rules = ss.MainWindow.apply_routing_rules.__get__(
            self.obj, ss.MainWindow)
        self.obj.update_status_bar = MagicMock()
        self.obj.show_status = MagicMock()

    def _sinks(self):
        return [
            {'index': '52', 'name': 'alsa_output'},
            {'index': '60', 'name': 'Media'},
            {'index': '61', 'name': 'Aux'},
        ]

    def test_url_pattern_routes_music_youtube(self):
        # Stream 42 has url music.youtube.com → should go to Media
        streams = [{'index': '42', 'app_name': 'Brave', 'media_name': 'Playback',
                    'sink': '52', 'url': 'https://music.youtube.com/watch?v=abc'}]
        self.obj.get_sinks = MagicMock(return_value=self._sinks())
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        calls = []
        self.obj.run_pactl = MagicMock(side_effect=lambda a: calls.append(a) or 'ok')
        self.obj.apply_routing_rules()
        self.assertIn(['move-sink-input', '42', 'Media'], calls)

    def test_url_pattern_routes_plain_youtube(self):
        # Stream 43 has url www.youtube.com → should go to Aux
        self.obj.stream_url_cache['43'] = 'https://www.youtube.com/watch?v=xyz'
        streams = [{'index': '43', 'app_name': 'Brave', 'media_name': 'Playback',
                    'sink': '52', 'url': 'https://www.youtube.com/watch?v=xyz'}]
        self.obj.get_sinks = MagicMock(return_value=self._sinks())
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        calls = []
        self.obj.run_pactl = MagicMock(side_effect=lambda a: calls.append(a) or 'ok')
        self.obj.apply_routing_rules()
        self.assertIn(['move-sink-input', '43', 'Aux'], calls)

    def test_rule_without_url_pattern_still_matches_on_app_name(self):
        # Backward compat: rule with no url_pattern matches all streams for that app
        self.obj.state['rules'] = [{'app_name': 'Firefox', 'sink': 'Aux'}]
        self.obj.stream_url_cache = {}
        streams = [{'index': '55', 'app_name': 'Firefox', 'media_name': 'Video',
                    'sink': '52', 'url': ''}]
        self.obj.get_sinks = MagicMock(return_value=self._sinks())
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        calls = []
        self.obj.run_pactl = MagicMock(side_effect=lambda a: calls.append(a) or 'ok')
        self.obj.apply_routing_rules()
        self.assertIn(['move-sink-input', '55', 'Aux'], calls)
```

- [ ] **Step 2: Run — all pass (implementation was done in Task 4)**

```bash
python -m pytest tests/test_stream_disambiguation.py::TestUrlPatternRules -v
```

Expected: 3 tests, all PASSED.

- [ ] **Step 3: Run full suite**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: all tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add tests/test_stream_disambiguation.py
git commit -m "test: add url_pattern routing tests"
```

---

## Task 6: `RulesDialog` url_pattern field + context menu prefill

**Files:**
- Modify: `SoundSwitch.py` (`RulesDialog.__init__`, `_init_ui`, `_refresh_list`, `_on_row_changed`, `_new_rule`, `_save_rule`, `open_rules_dialog_for_app`)

No unit tests for Qt dialog widgets; verify by running the app.

- [ ] **Step 1: Add `prefill_url` parameter to `RulesDialog.__init__`**

Replace the `__init__` signature and prefill block (lines 554–568):

```python
def __init__(self, state, save_state_cb, refresh_rules_cb, parent=None,
             prefill_app_name=None, prefill_url=None):
    super().__init__(parent)
    self.state = state
    self._save_state_cb = save_state_cb
    self._refresh_rules_cb = refresh_rules_cb
    self._prefill_active = False
    self.setWindowTitle('Manage Auto-Routing Rules')
    self.setModal(True)
    self.setMinimumWidth(500)
    self._init_ui()
    if prefill_app_name:
        self._prefill_active = True
        self._app_input.setText(prefill_app_name)
        if prefill_url:
            self._url_input.setText(prefill_url)
        self._sink_combo.setCurrentIndex(0)
        self._delete_btn.setEnabled(False)
```

- [ ] **Step 2: Add `_url_input` field to `RulesDialog._init_ui()`**

In `_init_ui()`, after the block that adds the app name label and input (after line ~596 `right.addWidget(self._app_input)`), insert:

```python
        right.addWidget(QLabel('URL contains (optional):'))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText('e.g. music.youtube.com')
        self._url_input.returnPressed.connect(self._save_rule)
        right.addWidget(self._url_input)
```

- [ ] **Step 3: Update `_refresh_list()` to show url_pattern in list items**

Replace `_refresh_list()` (lines 626–634):

```python
def _refresh_list(self):
    self._list.blockSignals(True)
    self._list.clear()
    for rule in self.state.get('rules', []):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, {'app_name': rule['app_name'], 'sink': rule['sink'],
                                    'url_pattern': rule.get('url_pattern', '')})
        url_part = f" @ {rule['url_pattern']}" if rule.get('url_pattern') else ''
        item.setData(Qt.DisplayRole, f"{rule['app_name']}{url_part} → {rule['sink']}")
        self._list.addItem(item)
    self._list.blockSignals(False)
```

Also update the identical block in `refresh_rules_list()` (line ~1576–1582, used for the sidebar rules list):

```python
def refresh_rules_list(self):
    self.rules_list.clear()
    for rule in self.state['rules']:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, {'app_name': rule['app_name'], 'sink': rule['sink'],
                                    'url_pattern': rule.get('url_pattern', '')})
        url_part = f" @ {rule['url_pattern']}" if rule.get('url_pattern') else ''
        item.setData(Qt.DisplayRole, f"{rule['app_name']}{url_part} → {rule['sink']}")
        self.rules_list.addItem(item)
```

- [ ] **Step 4: Update `_on_row_changed()` to populate `_url_input`**

Replace the populating lines inside `_on_row_changed()` (lines 646–650):

```python
    rule = self.state.get('rules', [])[row]
    self._app_input.setText(rule['app_name'])
    self._url_input.setText(rule.get('url_pattern', ''))
    idx = CUSTOM_SINKS.index(rule['sink']) if rule['sink'] in CUSTOM_SINKS else 0
    self._sink_combo.setCurrentIndex(idx)
    self._delete_btn.setEnabled(True)
```

- [ ] **Step 5: Update `_new_rule()` to clear `_url_input`**

Replace `_new_rule()` (lines 652–657):

```python
def _new_rule(self):
    self._prefill_active = False
    self._list.setCurrentRow(-1)
    self._app_input.clear()
    self._url_input.clear()
    self._sink_combo.setCurrentIndex(0)
    self._delete_btn.setEnabled(False)
```

- [ ] **Step 6: Update `_save_rule()` to read `url_pattern` and fix duplicate check**

Replace `_save_rule()` (lines 659–684):

```python
def _save_rule(self):
    app_name = self._app_input.text().strip()
    if not app_name:
        QMessageBox.warning(self, 'Missing App Name', 'Please enter an app name.')
        return
    sink = self._sink_combo.currentText()
    url_pattern = self._url_input.text().strip()
    row = self._list.currentRow()

    def is_duplicate(exclude_row):
        for i, r in enumerate(self.state.get('rules', [])):
            if i == exclude_row:
                continue
            if (r['app_name'].lower() == app_name.lower()
                    and r.get('url_pattern', '').lower() == url_pattern.lower()):
                return True
        return False

    if row >= 0:
        if is_duplicate(row):
            QMessageBox.warning(self, 'Duplicate Rule',
                                f"A rule for '{app_name}' with that URL pattern already exists.")
            return
        self.state['rules'][row] = {'app_name': app_name, 'sink': sink,
                                    **({'url_pattern': url_pattern} if url_pattern else {})}
    else:
        if is_duplicate(-1):
            QMessageBox.warning(self, 'Duplicate Rule',
                                f"A rule for '{app_name}' with that URL pattern already exists.")
            return
        rule = {'app_name': app_name, 'sink': sink}
        if url_pattern:
            rule['url_pattern'] = url_pattern
        self.state['rules'].append(rule)

    self._save_state_cb()
    self._refresh_rules_cb()
    self._refresh_list()
    self._new_rule()
```

- [ ] **Step 7: Update `open_rules_dialog_for_app()` to pass URL domain as prefill**

Replace `open_rules_dialog_for_app()` (lines 1971–1978):

```python
def open_rules_dialog_for_app(self, app_name, stream_index=None):
    prefill_url = ''
    if stream_index is not None:
        url = self.stream_url_cache.get(str(stream_index), '')
        prefill_url = _url_domain(url)
    RulesDialog(
        self.state,
        self.save_state,
        lambda: self.refresh_devices_and_sinks(force=True),
        parent=self,
        prefill_app_name=app_name,
        prefill_url=prefill_url,
    ).exec_()
```

- [ ] **Step 8: Pass `stream_index` from the context menu action in `show_stream_context_menu()`**

In `show_stream_context_menu()` (around line 1584), the `create_action` connects to `open_rules_dialog_for_app`. Update it to also pass the stream index:

```python
    # Before:
    create_action.triggered.connect(lambda: self.open_rules_dialog_for_app(app_name))

    # After:
    create_action.triggered.connect(
        lambda: self.open_rules_dialog_for_app(app_name, stream_index=stream_index))
```

- [ ] **Step 9: Run the app and verify the dialog**

```bash
source .venv/bin/activate && python3 SoundSwitch.py
```

- Open "Manage Rules…" — verify the "URL contains (optional)" field appears below "App name".
- Right-click a Brave stream with a URL tagged → "Create Rule" → verify both "App name: Brave" and "URL contains: music.youtube.com" are pre-filled.
- Save a rule with a url_pattern → verify the sidebar list shows `"Brave @ music.youtube.com → Media"`.

- [ ] **Step 10: Run all tests**

```bash
python -m pytest tests/test_stream_disambiguation.py -v
```

Expected: all tests PASSED.

- [ ] **Step 11: Commit**

```bash
git add SoundSwitch.py
git commit -m "feat: add url_pattern field to RulesDialog with auto-prefill from stream URL"
```

---

## Self-Review

**Spec coverage:**
| Spec requirement | Task |
|---|---|
| `get_mpris_browser_url()` querying Plasma Browser Integration | Task 1 |
| `_parse_dbus_metadata()` parsing `dbus-send` output | Task 1 |
| `stream_url_cache` in-memory dict | Task 2 |
| `update_stream_urls()` — stale removal, tagging, URL attachment | Task 2 |
| Wire `update_stream_urls()` into refresh cycle | Task 2 |
| Stream list shows URL domain as subtitle | Task 3 |
| `url_routes` domain-keyed persistent routing | Task 4 |
| Implicit learning via drag-and-drop in `move_sink_input()` | Task 4 |
| `url_pattern` field in named rules | Task 5 |
| Backward compat: rules without `url_pattern` still work | Task 5 |
| Manual overrides block all auto-routing | Task 4 |
| `RulesDialog` "URL contains" field | Task 6 |
| Context menu "Create Rule" pre-fills URL | Task 6 |
| Graceful fallback when MPRIS unavailable | Task 1 (returns None), Task 2 (no-op) |

**Placeholder scan:** None found. All steps include concrete code.

**Type consistency:**
- `stream_url_cache` keys are `str` (stream index as string from pactl). `update_stream_urls` uses `s['index']` directly. `apply_routing_rules()` calls `self.stream_url_cache.get(stream['index'], '')` — consistent.
- `_url_domain()` is called in `apply_routing_rules()`, `move_sink_input()` — both use the module-level function imported at test time. Consistent.
- `url_routes` keys are domain strings; `apply_routing_rules()` looks up by domain; `move_sink_input()` writes by domain. Consistent.
