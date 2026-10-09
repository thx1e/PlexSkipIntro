# -*- coding: utf-8 -*-
"""Kodi service: shows Skip Intro / Skip Credits buttons from Plex markers."""
import os
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from lib.plexlookup import LookupResult, find_episode, find_movie
from lib.settings_import import parse_kodi_settings
from lib.skiplogic import SkipController, button_timeout, skip_target

OLD_ADDON_ID = 'service.plexskipintro'
NAME = 'Skip Intro & Credits'
SKIP_BUTTON = 201
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
TICK = 0.5  # seconds between playback checks

ADDON_PATH = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('path'))
ICON = os.path.join(ADDON_PATH, 'resources', 'icon.png')


def log(message, level=xbmc.LOGINFO):
    xbmc.log('[service.plexskipintrocredits] %s' % message, level)


def notify(message, ms=5000):
    try:
        xbmcgui.Dialog().notification(NAME, message, ICON, ms, False)
    except Exception as exc:
        log('notification failed: %s' % exc, xbmc.LOGWARNING)


def get_str(addon, setting_id, default=''):
    try:
        value = addon.getSettingString(setting_id)
    except Exception:
        value = addon.getSetting(setting_id)
    return value if value else default


def set_str(addon, setting_id, value):
    try:
        addon.setSettingString(setting_id, value)
    except Exception:
        addon.setSetting(setting_id, value)


def get_bool(addon, setting_id, default=True):
    try:
        return addon.getSettingBool(setting_id)
    except Exception:
        value = (addon.getSetting(setting_id) or '').lower()
        return default if value == '' else value == 'true'


def get_int(addon, setting_id, default=10):
    try:
        return addon.getSettingInt(setting_id)
    except Exception:
        try:
            return int(float(addon.getSetting(setting_id)))
        except (TypeError, ValueError):
            return default


def short_error(exc, url):
    name = exc.__class__.__name__
    if name == 'Unauthorized':
        return 'token rejected (401), check the add-on settings'
    if 'Timeout' in name:
        return 'no answer from %s' % url
    if name in ('ConnectionError', 'NewConnectionError', 'MaxRetryError'):
        return 'cannot reach %s' % url
    text = str(exc) or name
    return text if len(text) <= 120 else text[:117] + '...'


def import_old_settings():
    """Fill an empty Plex URL and/or token from the original Plex TV Skip Intro add-on.

    Runs at every service start, so it also repairs a URL or token that an update reset to blank.
    """
    addon = xbmcaddon.Addon()
    have_url = bool(get_str(addon, 'plex_base_url').strip())
    have_token = bool(get_str(addon, 'auth_token').strip())
    if have_url and have_token:
        return
    path = 'special://profile/addon_data/%s/settings.xml' % OLD_ADDON_ID
    if not xbmcvfs.exists(path):
        log('Plex URL or token not set and no %s settings to import' % OLD_ADDON_ID)
        return
    handle = xbmcvfs.File(path)
    try:
        text = handle.read()
    finally:
        handle.close()
    values = parse_kodi_settings(text)
    imported = []
    if not have_url and values.get('plex_base_url'):
        set_str(addon, 'plex_base_url', values['plex_base_url'])
        imported.append('URL')
    if not have_token and values.get('auth_token'):
        set_str(addon, 'auth_token', values['auth_token'])
        imported.append('token')
    if not imported:
        log('%s has no Plex URL or token saved, nothing to import' % OLD_ADDON_ID)
        return
    log('imported Plex %s from %s' % (' and '.join(imported), OLD_ADDON_ID))
    notify('Imported Plex %s from Plex TV Skip Intro' % ' and '.join(imported))


def warn_if_old_addon_enabled():
    try:
        if xbmc.getCondVisibility('System.AddonIsEnabled(%s)' % OLD_ADDON_ID):
            log('%s is still enabled: both add-ons will show a button' % OLD_ADDON_ID, xbmc.LOGWARNING)
            notify('Disable "Plex TV Skip Intro" to avoid two Skip buttons', 8000)
    except Exception as exc:
        log('could not check %s: %s' % (OLD_ADDON_ID, exc), xbmc.LOGWARNING)


class SkipDialog(xbmcgui.WindowXMLDialog):
    """The Skip button. `label` and `target` are set before show()."""

    def __init__(self, *args, **kwargs):
        self.label = 'Skip Intro'
        self.target = 0.0
        self.closed = False

    def onInit(self):
        try:
            self.getControl(SKIP_BUTTON).setLabel(self.label)
        except Exception as exc:
            log('could not set the button label: %s' % exc, xbmc.LOGWARNING)

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.dismiss()

    def onClick(self, control_id):
        if control_id == SKIP_BUTTON:
            log('%s pressed: seeking to %.1f s' % (self.label, self.target))
            try:
                xbmc.Player().seekTime(self.target)
            except Exception as exc:
                log('seek failed: %s' % exc, xbmc.LOGERROR)
        self.dismiss()

    def dismiss(self):
        self.closed = True
        self.close()


class Service(xbmc.Monitor):

    def __init__(self):
        xbmc.Monitor.__init__(self)
        self.player = xbmc.Player()
        self.skips = SkipController()
        self.lock = threading.Lock()   # guards skips and generation (lookups run in threads)
        self.generation = 0            # bumped on every playback start/stop
        self.dialog = None
        self.dialog_until = 0.0
        self.worker = None
        self.item_kind = None          # 'episode' or 'movie' for the current markers
        self.load_settings()

    # --- settings -------------------------------------------------------------------
    def load_settings(self):
        addon = xbmcaddon.Addon()
        self.intro_enabled = get_bool(addon, 'intro_enabled', True)
        self.credits_enabled = get_bool(addon, 'credits_enabled', True)
        self.movie_credits_enabled = get_bool(addon, 'movie_credits_enabled', True)
        self.intro_timeout = get_int(addon, 'default_timeout', 10)
        self.credits_timeout = get_int(addon, 'credits_timeout', 10)

    def onSettingsChanged(self):
        self.load_settings()

    # --- playback events ------------------------------------------------------------
    def onNotification(self, sender, method, data):
        if method == 'Player.OnAVStart':
            self.start_lookup()
        elif method == 'Player.OnStop':
            self.reset()

    def reset(self):
        with self.lock:
            self.generation += 1
            self.skips.clear()
            self.item_kind = None
        self.close_dialog()

    def start_lookup(self):
        self.reset()
        with self.lock:
            generation = self.generation
        item = self.playing_item()
        if item is None:
            return
        if item['kind'] == 'movie' and not self.movie_credits_enabled:
            log('%s: Skip Credits for movies is off, no lookup' % item['label'])
            return
        self.worker = threading.Thread(target=self.lookup, args=(generation, item))
        self.worker.daemon = True
        self.worker.start()

    def playing_item(self):
        """What Kodi is playing, as a dict for the lookup, or None if it is not a library episode or movie."""
        try:
            if not self.player.isPlayingVideo():
                return None
            tag = self.player.getVideoInfoTag()
            media_type = tag.getMediaType() if hasattr(tag, 'getMediaType') else ''
            path = self.player.getPlayingFile()
            if media_type in ('', 'episode'):
                title, season, episode = tag.getTVShowTitle(), tag.getSeason(), tag.getEpisode()
                if title and season >= 0 and episode >= 1:
                    return {'kind': 'episode', 'title': title, 'season': season, 'episode': episode,
                            'path': path, 'label': '%s S%02dE%02d' % (title, season, episode)}
            if media_type == 'movie':
                title, year = tag.getTitle(), tag.getYear()
                if title:
                    year = year if year and year > 0 else 0
                    return {'kind': 'movie', 'title': title, 'original': tag.getOriginalTitle(), 'year': year,
                            'path': path, 'label': '%s (%d)' % (title, year) if year else title}
        except Exception as exc:
            log('could not read what is playing: %s' % exc, xbmc.LOGWARNING)
            return None
        log('not a TV episode or movie from the Kodi library (type=%r), skipping lookup' % media_type)
        return None

    def lookup(self, generation, item):
        label = item['label']
        addon = xbmcaddon.Addon()
        url = get_str(addon, 'plex_base_url').strip().rstrip('/')
        token = get_str(addon, 'auth_token').strip()
        show_result = get_bool(addon, 'show_lookup_result', True)
        if not url:
            log('no Plex URL set', xbmc.LOGWARNING)
            notify('No Plex URL set: open the add-on settings')
            return
        if not token:
            log('no Plex token set', xbmc.LOGWARNING)
            notify('No Plex token set: open the add-on settings')
            return
        log('looking up %s (playing %s)' % (label, item['path']))
        started = time.time()
        try:
            from plexapi.server import PlexServer
            server = PlexServer(url, token, timeout=10)
            if item['kind'] == 'movie':
                result = find_movie(server, item['title'], item['original'], item['year'], item['path'], log=log)
            else:
                result = find_episode(server, item['title'], item['season'], item['episode'], item['path'], log=log)
        except Exception as exc:
            log('lookup of %s failed: %r' % (label, exc), xbmc.LOGERROR)
            result = LookupResult(LookupResult.ERROR, message=short_error(exc, url))
        with self.lock:
            if generation != self.generation:
                log('playback changed while looking up %s, result dropped' % label)
                return
            self.skips.set_markers(result.markers)
            self.item_kind = item['kind']
        summary = result.summary(label, item['kind'])
        log('%s (%.1f s)' % (summary, time.time() - started))
        if show_result or result.status == LookupResult.ERROR:
            notify(summary)

    # --- main loop ------------------------------------------------------------------
    def run(self):
        log('started, version %s' % xbmcaddon.Addon().getAddonInfo('version'))
        try:
            import_old_settings()
        except Exception as exc:
            log('settings import failed: %s' % exc, xbmc.LOGWARNING)
        warn_if_old_addon_enabled()
        if self.player.isPlayingVideo():
            self.start_lookup()  # service (re)started in the middle of an episode
        while not self.abortRequested():
            if self.waitForAbort(TICK):
                break
            try:
                self.tick()
            except Exception as exc:
                log('playback check failed: %s' % exc, xbmc.LOGERROR)
        self.close_dialog()
        log('stopped')

    def tick(self):
        if self.dialog is not None and (self.dialog.closed or time.time() >= self.dialog_until):
            self.close_dialog()
        if not self.player.isPlayingVideo():
            return
        now = self.player.getTime()
        with self.lock:
            credits_on = self.movie_credits_enabled if self.item_kind == 'movie' else self.credits_enabled
            marker = self.skips.due(now, self.intro_enabled, credits_on, can_show=self.dialog is None)
        if marker is None:
            return
        setting = self.intro_timeout if marker.kind == 'intro' else self.credits_timeout
        self.open_dialog(marker, now, skip_target(marker, self.player.getTotalTime()),
                         button_timeout(marker, now, setting))

    def open_dialog(self, marker, now, target, timeout):
        dialog = SkipDialog('script-dialog.xml', ADDON_PATH, 'Default', '720p')
        dialog.label = 'Skip Intro' if marker.kind == 'intro' else 'Skip Credits'
        dialog.target = target
        self.dialog = dialog
        self.dialog_until = time.time() + timeout
        log('showing %s at %.1f s (skips to %.1f s, hides after %.0f s)' % (dialog.label, now, target, timeout))
        dialog.show()

    def close_dialog(self):
        dialog, self.dialog = self.dialog, None
        if dialog is None:
            return
        try:
            if not dialog.closed:
                dialog.closed = True
                dialog.close()
        except Exception as exc:
            log('closing the button failed: %s' % exc, xbmc.LOGWARNING)
        del dialog
