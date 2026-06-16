import re
import sys
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from SoundSwitch import _parse_dbus_metadata, _url_domain

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
        result = _parse_dbus_metadata(SAMPLE_DBUS_OUTPUT)
        self.assertNotIn('CanControl', result)

    def test_empty_output_returns_empty_dict(self):
        self.assertEqual(_parse_dbus_metadata(''), {})

    def test_extracts_other_keys_when_url_absent(self):
        result = _parse_dbus_metadata("no url here\nstring \"xesam:title\"\nvariant string \"hi\"")
        self.assertEqual(result.get('xesam:title'), 'hi')
        self.assertNotIn('xesam:url', result)


class TestGetMprisBrowserUrl(unittest.TestCase):
    """Tests for MainWindow.get_mpris_browser_url() via mocked subprocess."""

    def _make_window_mock(self):
        """Return a minimal object with get_mpris_browser_url bound to it."""
        import SoundSwitch as ss
        obj = ss.MainWindow.__new__(ss.MainWindow)
        obj.get_mpris_browser_url = ss.MainWindow.get_mpris_browser_url.__get__(obj, ss.MainWindow)
        return obj

    def test_returns_url_and_title_on_success(self):
        obj = self._make_window_mock()
        fake_result = MagicMock()
        fake_result.returncode = 0
        fake_result.stdout = SAMPLE_DBUS_OUTPUT
        with patch('SoundSwitch.subprocess.run', return_value=fake_result):
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
        with patch('SoundSwitch.subprocess.run', return_value=fake_result):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_subprocess_error(self):
        obj = self._make_window_mock()
        with patch('SoundSwitch.subprocess.run', side_effect=FileNotFoundError):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_timeout(self):
        obj = self._make_window_mock()
        with patch('SoundSwitch.subprocess.run', side_effect=subprocess.TimeoutExpired('dbus-send', 2)):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)

    def test_returns_none_on_nonzero_returncode(self):
        obj = self._make_window_mock()
        fake_result = MagicMock()
        fake_result.returncode = 1
        fake_result.stdout = ''
        with patch('SoundSwitch.subprocess.run', return_value=fake_result):
            result = obj.get_mpris_browser_url()
        self.assertIsNone(result)


class TestUpdateStreamUrls(unittest.TestCase):
    """Tests for the stream URL caching logic."""

    def setUp(self):
        """Build a minimal MainWindow-like object with stream_url_cache."""
        import SoundSwitch as ss
        self.obj = ss.MainWindow.__new__(ss.MainWindow)
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


class TestUrlRoutesMatching(unittest.TestCase):
    def test_domain_extracted_from_full_url(self):
        self.assertEqual(_url_domain('https://music.youtube.com/watch?v=abc'), 'music.youtube.com')

    def test_domain_extracted_from_root_url(self):
        self.assertEqual(_url_domain('https://music.youtube.com/'), 'music.youtube.com')

    def test_empty_url_returns_empty_string(self):
        self.assertEqual(_url_domain(''), '')

    def test_non_http_url_returns_empty_string(self):
        self.assertEqual(_url_domain('spotify:track:123'), '')


class TestApplyUrlRoutes(unittest.TestCase):
    """Integration-style tests for the url_routes routing layer."""

    def setUp(self):
        import SoundSwitch as ss
        self.obj = ss.MainWindow.__new__(ss.MainWindow)
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
        sinks = self._make_sinks()
        self.obj.get_sinks = MagicMock(return_value=sinks)
        self.obj.get_sink_inputs = MagicMock(return_value=streams)
        self.obj.update_hidden_streams = MagicMock()
        self.obj.run_pactl = MagicMock(return_value='ok')
        self.obj.apply_routing_rules()
        self.obj.run_pactl.assert_not_called()


class TestMoveSinkInputLearning(unittest.TestCase):
    def setUp(self):
        import SoundSwitch as ss
        self.obj = ss.MainWindow.__new__(ss.MainWindow)
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
        self.obj.stream_url_cache = {}
        self.obj.run_pactl = MagicMock(return_value='ok')
        self.obj.move_sink_input('42', 'Aux')
        self.assertEqual(self.obj.state['url_routes'], {})

if __name__ == '__main__':
    unittest.main()
