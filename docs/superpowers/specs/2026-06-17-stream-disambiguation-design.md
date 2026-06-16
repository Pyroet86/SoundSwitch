# Stream Disambiguation via MPRIS URL Correlation

**Date:** 2026-06-17  
**Status:** Approved  
**Scope:** `SoundSwitch.py` only — single-file change

---

## Problem

Brave browser (and other Chromium-based browsers) route all tab audio through a single shared audio service process. Every audio stream therefore carries identical PipeWire metadata: `application.name = "Brave"`, `media.name = "Playback"`, same PID. There is no native way to tell a YouTube stream from a YouTube Music stream. Auto-routing rules keyed on `app_name` alone cannot distinguish them, so when a stream disconnects and reconnects it may land in the wrong sink.

---

## Solution Overview

Two complementary layers:

1. **MPRIS URL correlation** — query KDE Plasma Browser Integration over D-Bus to get the active tab URL and tag each browser stream with it. Displayed as a subtitle in the stream list.
2. **URL-aware routing** — `url_routes` persistent memory (built implicitly from drag history) and optional `url_pattern` field on named rules (set explicitly in the Rules dialog).

---

## Architecture

### New in-memory state

```python
# On MainWindow.__init__
self.stream_url_cache: dict[str, str] = {}   # stream_index → full URL
```

### New methods

#### `get_mpris_browser_url() -> dict | None`

Calls `dbus-send` to query `org.mpris.MediaPlayer2.plasma-browser-integration` for the `Player` properties. Parses `xesam:url` and `xesam:title` from the reply. Returns `{"url": "https://music.youtube.com/...", "title": "Black & White"}` or `None` if the service is unavailable or the URL is not an `http(s)` URL.

This is the only point of contact with D-Bus. Uses subprocess exactly like `run_pactl()`.

#### `update_stream_urls(sink_inputs: list[dict])`

Called inside `refresh_ui()` immediately after `get_sink_inputs()`.

1. Remove entries from `stream_url_cache` for stream indices that no longer exist.
2. Identify browser streams: those whose `app_name` is in a known set (`{"Brave", "Firefox", "Chromium", "Chrome"}`).
3. For each browser stream not yet in the cache, call `get_mpris_browser_url()` and store the result under that stream's index.
4. After tagging, attach the cached URL (if any) back onto each stream dict as `stream["url"]` so downstream code can read it without touching the cache directly.

When two browser streams appear in the same tick and MPRIS shows only one URL, only the first untagged stream gets tagged. The second remains untagged until the next tick where MPRIS has switched. This converges within one or two 2-second cycles as the user interacts with each tab — no error state, just a brief delay.

### Modified methods

#### `refresh_ui()`

After the existing `sink_inputs = self.get_sink_inputs()` call, add:

```python
self.update_stream_urls(sink_inputs)
```

#### Stream list item display

The subtitle line (currently `media_name`) becomes the **URL domain** when a URL is cached for that stream, falling back to `media_name` when not. Domain extraction: `urllib.parse.urlparse(url).netloc` or simple string split — no new import needed beyond `urllib.parse` which is stdlib.

Example display:
```
Brave                    Brave
music.youtube.com        www.youtube.com
```

#### `apply_routing_rules()`

Routing priority (highest to lowest):

1. **`url_routes`** — exact URL match against `state.get("url_routes", {})`. If `stream["url"]` is in `url_routes`, move stream to the mapped sink (unless already there or a manual override is in effect).
2. **Named rules with `url_pattern`** — for rules that have a `url_pattern` field, check `url_pattern in stream.get("url", "")`. More specific match wins; first matching rule in the list wins among ties.
3. **Named rules without `url_pattern`** (existing behaviour) — match on `app_name` only.

Manual overrides continue to block all auto-routing as before.

#### `move_sink_input()`

After a successful manual move: if `stream_url_cache` has a URL for that stream index, write `state["url_routes"][url] = sink_name` and call `save_state()`. This is the implicit learning step — drag once, remembered forever.

#### `RulesDialog`

- Add a `QLineEdit` labelled "URL contains (optional)" below the existing app name field.
- Rule save/load includes the optional `url_pattern` key (absent means app_name-only rule, preserving full backward compatibility).
- `prefill_url` parameter added alongside the existing `prefill_app_name`; pre-populates the new field when opening the dialog from a tagged stream's context menu.
- Display in the rules list: `"Brave @ music.youtube.com → Media"` when `url_pattern` is set, `"Firefox → Aux"` when not.

---

## State schema addition

```json
"url_routes": {
  "https://music.youtube.com/watch?v=...": "Media",
  "https://www.youtube.com/watch?v=...":   "Aux"
}
```

Keys are full URLs as returned by MPRIS (may include path/query). The match in `apply_routing_rules()` is an exact dict lookup, so two different YouTube videos get separate entries. If this grows large it can be pruned later; for now it is unbounded.

> **Note:** `url_pattern` in named rules uses substring matching, so one rule `music.youtube.com → Media` covers all YouTube Music URLs regardless of which song is playing. `url_routes` is per-URL and is auto-populated; named rules are per-pattern and are manually created.

---

## Graceful degradation

| Condition | Behaviour |
|---|---|
| Plasma Browser Integration not installed / not running | `get_mpris_browser_url()` returns `None`; cache stays empty; app behaves exactly as today |
| Non-browser app stream | No MPRIS query attempted; shown and routed as before |
| MPRIS shows non-browser URL (e.g. Spotify) | URL starts with `spotify:` → ignored (only `http(s)` URLs are stored) |
| Both streams reconnect simultaneously | One stream tagged immediately, second tagged on next tick; brief routing delay, no error |

---

## Files changed

| File | Change |
|---|---|
| `SoundSwitch.py` | All changes (new methods, modified methods, new state key) |
| `routing_state.json` | New `url_routes` key added on first manual move of a browser stream |

No new Python packages. `urllib.parse` is stdlib. `dbus-send` is available on all KDE Plasma systems.
