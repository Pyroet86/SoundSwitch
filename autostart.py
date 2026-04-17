import os
import sys

_DESKTOP_PATH = os.path.expanduser('~/.config/autostart/soundswitch.desktop')
_SOUNDSWITCH_PY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'SoundSwitch.py')

_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=SoundSwitch
Exec={python} {script}{minimized}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""


def is_enabled() -> bool:
    return os.path.isfile(_DESKTOP_PATH)


def is_minimized() -> bool:
    if not is_enabled():
        return True
    with open(_DESKTOP_PATH) as f:
        for line in f:
            if line.startswith('Exec='):
                return '--minimized' in line
    return False


def enable(start_minimized: bool = True) -> None:
    os.makedirs(os.path.dirname(_DESKTOP_PATH), exist_ok=True)
    minimized_flag = ' --minimized' if start_minimized else ''
    content = _DESKTOP_TEMPLATE.format(
        python=sys.executable,
        script=_SOUNDSWITCH_PY,
        minimized=minimized_flag,
    )
    with open(_DESKTOP_PATH, 'w') as f:
        f.write(content)


def disable() -> None:
    if os.path.isfile(_DESKTOP_PATH):
        os.remove(_DESKTOP_PATH)
