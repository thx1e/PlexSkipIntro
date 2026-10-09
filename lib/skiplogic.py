# -*- coding: utf-8 -*-
"""When to offer a skip button. Pure logic: the Kodi layer feeds it playback times."""

SHOW_MARGIN = 2.0     # never offer a skip during the last 2 s of a marker
BACKWARD_JUMP = 2.0   # playback moving back more than this re-arms markers


class SkipController(object):
    def __init__(self):
        self.markers = []
        self.last_time = None

    def set_markers(self, markers):
        self.markers = list(markers)
        for marker in self.markers:
            marker.shown = False
        self.last_time = None

    def clear(self):
        self.set_markers([])

    def due(self, now, intro_enabled=True, credits_enabled=True, can_show=True):
        """Marker whose button should appear at playback time `now` (seconds), or None.

        A returned marker is flagged as shown, so it is offered once per pass. Seeking
        back (or restarting) to before the end of a marker offers it again; the forward
        seek done by the Skip button does not.
        """
        if self.last_time is not None and now < self.last_time - BACKWARD_JUMP:
            for marker in self.markers:
                if now < marker.end - SHOW_MARGIN:
                    marker.shown = False
        self.last_time = now
        if not can_show:
            return None
        for marker in self.markers:
            if marker.kind == 'intro' and not intro_enabled:
                continue
            if marker.kind == 'credits' and not credits_enabled:
                continue
            if not marker.shown and marker.start <= now < marker.end - SHOW_MARGIN:
                marker.shown = True
                return marker
        return None


def skip_target(marker, total_time):
    """Where the Skip button seeks to: the marker end, but not past the last second of the file."""
    target = marker.end
    if total_time and total_time > 1.0:
        target = min(target, total_time - 1.0)
    return max(target, 0.0)


def button_timeout(marker, now, setting):
    """How long the button stays up: the setting, but not past the end of the marker."""
    try:
        setting = float(setting)
    except (TypeError, ValueError):
        setting = 10.0
    if setting <= 0:
        setting = 10.0
    return max(1.0, min(setting, marker.end - now))
