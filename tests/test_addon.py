"""End-to-end test of service.plexskipintrocredits outside Kodi.

Real add-on code + the add-on's bundled plexapi 4.8, talking HTTP to a fake Plex server,
with stub xbmc* modules standing in for Kodi.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)  # repo root by default
sys.path.insert(0, os.path.join(HERE, 'kodistubs'))
sys.path.insert(0, ADDON)
sys.path.insert(0, HERE)

import xbmc        # noqa: E402  (stubs)
import xbmcaddon   # noqa: E402
import xbmcgui     # noqa: E402
import xbmcvfs     # noqa: E402
import fakeplex    # noqa: E402

xbmcaddon.load_defaults(ADDON)
PROFILE = tempfile.mkdtemp()
xbmcvfs.PROFILE = PROFILE
SERVER, URL = fakeplex.start()

old_dir = os.path.join(PROFILE, 'addon_data', 'service.plexskipintro')
os.makedirs(old_dir)
with open(os.path.join(old_dir, 'settings.xml'), 'w', encoding='utf-8') as handle:
    handle.write('<settings version="2">\n'
                 '    <setting id="auth_token">GOODTOKEN</setting>\n'
                 '    <setting id="default_timeout" default="true">10</setting>\n'
                 '    <setting id="plex_base_url">%s</setting>\n'
                 '</settings>\n' % URL)

from lib import addon as A                          # noqa: E402
from lib.plexlookup import Marker, file_basename, title_variants  # noqa: E402
from lib.settings_import import parse_kodi_settings  # noqa: E402
from lib.skiplogic import button_timeout, skip_target  # noqa: E402

RESULTS = []


def check(cond, what):
    RESULTS.append((bool(cond), what))
    print('%s  %s' % ('PASS' if cond else 'FAIL', what))


def last_note():
    return xbmcgui.NOTIFICATIONS[-1] if xbmcgui.NOTIFICATIONS else ''


def play(svc, title, season, episode, path, mediatype='episode', total=1330.0, join=True):
    xbmc.STATE.reset()
    xbmc.STATE.playing = True
    xbmc.STATE.tag = xbmc.InfoTagVideo(title, season, episode, mediatype)
    xbmc.STATE.file = path
    xbmc.STATE.total = total
    svc.worker = None
    svc.onNotification('xbmc', 'Player.OnAVStart', '{}')
    if join and svc.worker is not None:
        svc.worker.join(20)


def play_movie(svc, title, year, path, original='', total=9000.0, join=True):
    xbmc.STATE.reset()
    xbmc.STATE.playing = True
    xbmc.STATE.tag = xbmc.InfoTagVideo(mediatype='movie', movie_title=title, year=year, original=original)
    xbmc.STATE.file = path
    xbmc.STATE.total = total
    svc.worker = None
    svc.onNotification('xbmc', 'Player.OnAVStart', '{}')
    if join and svc.worker is not None:
        svc.worker.join(20)


def marker_labels(svc):
    return [m.label() for m in svc.skips.markers]


def at(svc, seconds):
    xbmc.STATE.time = seconds
    svc.tick()
    return svc.dialog


SMB = 'smb://nas/media'

# --- pure helpers ------------------------------------------------------------------
check(file_basename(SMB + '/tv/South%20Park/Season%2029/South Park - S29E02.mkv') == 'south park - s29e02.mkv',
      'file name from a URL-encoded smb:// path')
check(file_basename(r'C:\TV\Show\Ep.MKV') == 'ep.mkv', 'file name from a Windows path')
check(title_variants('Doctor Who (2005)') == ['Doctor Who (2005)', 'Doctor Who'], 'title retried without (year)')
check(parse_kodi_settings('<settings><setting id="auth_token" value="X" /></settings>') == {'auth_token': 'X'},
      'legacy settings.xml format parsed')
check(parse_kodi_settings('not xml') == {}, 'broken settings.xml ignored')
credits = Marker('credits', 1295, 1321)
check(skip_target(credits, 1330) == 1321 and skip_target(credits, 1320) == 1319,
      'credits skip target clamped to 1 s before the end')
intro = Marker('intro', 4, 35)
check(button_timeout(intro, 4.5, 10) == 10 and button_timeout(intro, 30, 10) == 5,
      'button timeout capped at the marker end')

# --- settings import ------------------------------------------------------------------
A.import_old_settings()
check(xbmcaddon.SETTINGS['auth_token'] == 'GOODTOKEN' and xbmcaddon.SETTINGS['plex_base_url'] == URL,
      'URL and token imported from service.plexskipintro')
check('Imported' in last_note(), 'import shown on screen')
n = len(xbmcgui.NOTIFICATIONS)
A.import_old_settings()
check(len(xbmcgui.NOTIFICATIONS) == n, 'no second import once a token is set')

xbmcaddon.SETTINGS['plex_base_url'] = ''        # e.g. reset to the blank default by an update
A.import_old_settings()
check(xbmcaddon.SETTINGS['plex_base_url'] == URL and last_note() == 'Imported Plex URL from Plex TV Skip Intro',
      'blank URL refilled from the old add-on on its own: %r' % last_note())

xbmc.COND['System.AddonIsEnabled(service.plexskipintro)'] = True
A.warn_if_old_addon_enabled()
check('Disable "Plex TV Skip Intro"' in last_note(), 'warns while the old add-on is still enabled')

svc = A.Service()

# --- South Park S29E02 from the TV Shows folder -----------------------------------------
del fakeplex.REQUESTS[:]
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check(marker_labels(svc) == ['intro 0:04-0:35', 'credits 21:35-22:01'],
      'S29E02 markers read (commercial marker ignored): %s' % marker_labels(svc))
check(last_note() == 'South Park S29E02 (TV Shows): intro 0:04-0:35, credits 21:35-22:01',
      'lookup result on screen: %r' % last_note())
check(not any(r.startswith('/library/sections/3/') for r in fakeplex.REQUESTS), 'movie library not searched')
check(any(r.startswith('/library/sections/2/all') for r in fakeplex.REQUESTS), 'ETV library searched too')

check(at(svc, 2.0) is None, 'no button before the intro')
dialog = at(svc, 4.5)
check(dialog is not None and dialog.visible and dialog.label == 'Skip Intro', 'Skip Intro button at 0:04')
check(dialog is not None and dialog.getControl(201).label == 'Skip Intro', 'button label set on screen')
check(dialog is not None and dialog._args[:2] == ('script-dialog.xml', A.ADDON_PATH), 'dialog built from the skin xml')
check(dialog is not None and dialog.target == 35.0, 'skip target = intro end (35 s)')
check(abs((svc.dialog_until - A.time.time()) - 10) < 1, 'button stays 10 s')
dialog.onClick(201)
check(xbmc.STATE.seeks[-1] == 35.0, 'pressing Skip seeks to 35 s')
check(at(svc, 35.0) is None, 'button closed after skipping, not shown again')
check(at(svc, 40.0) is None, 'nothing after the intro')
dialog = at(svc, 10.0)
check(dialog is not None and dialog.label == 'Skip Intro', 'seeking back into the intro offers it again')
dialog.onAction(xbmcgui.Action(92))
check(at(svc, 12.0) is None, 'Back closes it and it stays closed')
dialog = at(svc, 1296.0)
check(dialog is not None and dialog.label == 'Skip Credits' and dialog.target == 1321.0,
      'Skip Credits at 21:36, skips to 22:01')
svc.dialog_until = 0
check(at(svc, 1297.0) is None, 'button hides after its timeout and is not repeated')

svc.onNotification('xbmc', 'Player.OnStop', '{}')
check(svc.skips.markers == [] and svc.dialog is None, 'stop clears markers')

# --- settings: intro off ----------------------------------------------------------------
xbmcaddon.SETTINGS['intro_enabled'] = 'false'
svc.onSettingsChanged()
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check(at(svc, 5.0) is None, 'intro button off when disabled in settings')
check(at(svc, 1296.0) is not None, 'credits button still on')
xbmcaddon.SETTINGS['intro_enabled'] = 'true'
svc.onSettingsChanged()

# --- not from the Kodi library -----------------------------------------------------------
play(svc, '', -1, -1, SMB + '/downloads/random clip.mkv', mediatype='')
check(svc.worker is None and svc.skips.markers == [], 'files played outside the Kodi library are not looked up')

# --- post-credits scene (Rick and Morty) ------------------------------------------------------
play(svc, 'Rick and Morty', 7, 1, SMB + '/tv/Rick and Morty/Season 07/Rick and Morty - S07E01.mkv', total=1320.0)
check(marker_labels(svc) == ['intro 2:30-3:02', 'credits 20:30-21:10'], 'Rick and Morty markers: %s' % marker_labels(svc))
dialog = at(svc, 1231.0)
check(dialog is not None and dialog.label == 'Skip Credits' and dialog.target == 1270.0,
      'Skip Credits targets the end of the credits (21:10), not the end of the file (22:00)')
dialog.onClick(201)
check(xbmc.STATE.seeks[-1] == 1270.0, 'skip lands on the post-credits scene')
check(at(svc, 1272.0) is None and at(svc, 1300.0) is None, 'no button while the post-credits scene plays')

# --- movies -----------------------------------------------------------------------------
MOV = SMB + '/movies'
play_movie(svc, 'Inception', 2010, MOV + '/Inception (2010)/Inception (2010).mkv', total=8890.0)
check(last_note() == 'Inception (2010) (Movies): credits 2:21:00-2:28:00', 'movie found: %r' % last_note())
check(not any(r.startswith('/library/sections/1/all') for r in fakeplex.REQUESTS[-6:]),
      'movie lookup does not search TV libraries')
check(at(svc, 8000.0) is None, 'no button before the credits')
dialog = at(svc, 8461.0)
check(dialog is not None and dialog.label == 'Skip Credits' and dialog.target == 8880.0,
      'movie Skip Credits at 2:21:01, skips to 2:28:00')
dialog.onClick(201)

play_movie(svc, 'Avengers: Endgame', 2019, MOV + '/Avengers Endgame (2019)/Avengers Endgame (2019).mkv', total=10860.0)
dialog = at(svc, 10201.0)
check(dialog is not None and dialog.target == 10500.0, 'first credits marker skips to the mid-credits scene (2:55:00)')
dialog.onClick(201)
check(at(svc, 10500.0) is None and at(svc, 10530.0) is None, 'mid-credits scene plays without a button')
dialog = at(svc, 10561.0)
check(dialog is not None and dialog.label == 'Skip Credits' and dialog.target == 10850.0,
      'second credits marker gets its own button')
svc.onNotification('xbmc', 'Player.OnStop', '{}')

play_movie(svc, 'Dune', 2021, MOV + '/elsewhere/dune.2021.2160p.mkv')
check(last_note() == 'Dune (2021) (Movies): credits 2:30:00-2:35:00', 'remake: the year picks Dune 2021: %r' % last_note())
play_movie(svc, 'Dune', 1984, MOV + '/Dune (1984)/Dune (1984).mkv')
check(last_note() == 'Dune (1984) (Movies): no credits markers in Plex yet', 'remake: Dune 1984 by file and year: %r' % last_note())

play_movie(svc, 'Amélie', 2001, MOV + '/other/amelie.2001.mkv', original="Le Fabuleux Destin d'Amélie Poulain")
check(last_note().startswith('Amélie (2001) (Movies): credits'), 'found by original title: %r' % last_note())

play_movie(svc, 'The Intouchables', 2011, MOV + '/Intouchables (2011)/Intouchables (2011).mkv')
check(last_note().startswith('The Intouchables (2011) (Movies): credits'),
      'translated title not in Plex: found by year + file name: %r' % last_note())

play_movie(svc, 'Nonexistent Film', 2020, MOV + '/Nonexistent Film (2020)/Nonexistent Film (2020).mkv')
check(last_note() == 'Nonexistent Film (2020): not found in any Plex movie library', 'missing movie reported')

xbmcaddon.SETTINGS['credits_enabled'] = 'false'          # TV credits off, movie credits still on
svc.onSettingsChanged()
play_movie(svc, 'Inception', 2010, MOV + '/Inception (2010)/Inception (2010).mkv', total=8890.0)
check(at(svc, 8461.0) is not None, 'TV credits switch does not affect movies')
xbmcaddon.SETTINGS['credits_enabled'] = 'true'
xbmcaddon.SETTINGS['movie_credits_enabled'] = 'false'
svc.onSettingsChanged()
play_movie(svc, 'Inception', 2010, MOV + '/Inception (2010)/Inception (2010).mkv', total=8890.0)
check(svc.worker is None and svc.skips.markers == [], 'movies not looked up when movie credits are off')
xbmcaddon.SETTINGS['movie_credits_enabled'] = 'true'
svc.onSettingsChanged()
svc.onNotification('xbmc', 'Player.OnStop', '{}')

# --- library choice --------------------------------------------------------------------
play(svc, 'South Park', 10, 5, SMB + '/etv/South Park/Season 10/South Park - S10E05 - Fat Camp.mkv')
check(last_note() == 'South Park S10E05 (ETV): no intro/credits markers in Plex yet',
      'ETV-only episode found in the ETV library: %r' % last_note())

play(svc, 'South Park', 29, 2, SMB + '/etv/South Park/Season 29/South.Park.S29E02.1080p.WEB.mkv')
check(last_note().startswith('South Park S29E02 (ETV): no intro/credits'),
      'same episode in two libraries: the copy Kodi is playing wins: %r' % last_note())

play(svc, 'South Park', 29, 2, SMB + '/elsewhere/south park 29x02.mkv')
check(last_note().startswith('South Park S29E02 (TV Shows): intro'),
      'no file match: the copy with markers wins: %r' % last_note())

play(svc, 'South Park', 99, 1, SMB + '/tv/South Park/Season 99/x.mkv')
check(last_note() == 'South Park S99E01: not found in any Plex TV library', 'missing episode reported')

play(svc, 'The Office', 2, 1, SMB + '/tv/The Office (US)/Season 02/The Office (US) - S02E01.mkv')
check(last_note().startswith('The Office S02E01 (TV Shows): intro 1:00-1:30'),
      'partial title: file name picks the US show: %r' % last_note())

play(svc, 'Doctor Who (2005)', 1, 1, SMB + '/tv/Doctor Who (2005)/Season 01/Doctor Who (2005) - S01E01 - Rose.mkv')
check(last_note().startswith('Doctor Who (2005) S01E01 (TV Shows): intro 2:00-2:30'),
      'Kodi title with (year) still found: %r' % last_note())

# --- errors --------------------------------------------------------------------------
xbmcaddon.SETTINGS['show_lookup_result'] = 'false'
xbmcaddon.SETTINGS['auth_token'] = 'WRONG'
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check('token rejected (401)' in last_note() and svc.skips.markers == [],
      'bad token shown even with lookup results off: %r' % last_note())
xbmcaddon.SETTINGS['auth_token'] = 'GOODTOKEN'

xbmcaddon.SETTINGS['plex_base_url'] = 'http://127.0.0.1:1'
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check('cannot reach http://127.0.0.1:1' in last_note(), 'unreachable Plex shown: %r' % last_note())
xbmcaddon.SETTINGS['plex_base_url'] = URL

n = len(xbmcgui.NOTIFICATIONS)
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check(len(xbmcgui.NOTIFICATIONS) == n and len(svc.skips.markers) == 2, 'lookup result hidden when turned off')
xbmcaddon.SETTINGS['show_lookup_result'] = 'true'

xbmcaddon.SETTINGS['auth_token'] = ''
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check(last_note() == 'No Plex token set: open the add-on settings', 'missing token reported')
xbmcaddon.SETTINGS['auth_token'] = 'GOODTOKEN'

xbmcaddon.SETTINGS['plex_base_url'] = ''
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv')
check(last_note() == 'No Plex URL set: open the add-on settings', 'missing URL reported')
xbmcaddon.SETTINGS['plex_base_url'] = URL

# --- playback changes while a lookup is running ----------------------------------------------
fakeplex.SLOW['allLeaves'] = 0.6
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv', join=False)
worker = svc.worker
svc.onNotification('xbmc', 'Player.OnStop', '{}')
worker.join(20)
check(svc.skips.markers == [] and any('result dropped' in m for _, m in xbmc.LOG),
      'lookup finishing after stop is dropped')

play(svc, 'South Park', 10, 5, SMB + '/etv/South Park/Season 10/South Park - S10E05 - Fat Camp.mkv', join=False)
first = svc.worker
play(svc, 'South Park', 29, 2, SMB + '/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv', join=False)
second = svc.worker
first.join(20)
second.join(20)
check(marker_labels(svc) == ['intro 0:04-0:35', 'credits 21:35-22:01'],
      'next episode started mid-lookup: only the newest result is used')
fakeplex.SLOW['allLeaves'] = 0.0

# --- service loop smoke test ---------------------------------------------------------------
svc2 = A.Service()
calls = [0]


def wait_for_abort(timeout):
    calls[0] += 1
    if svc2.worker is not None:
        svc2.worker.join(20)
    return calls[0] >= 4


svc2.waitForAbort = wait_for_abort
xbmc.STATE.time = 5.0
del xbmc.LOG[:]
svc2.run()
logs = [m for _, m in xbmc.LOG]
check(any(('started, version %s' % xbmcaddon.INFO['version']) in m for m in logs) and any(m.endswith('stopped') for m in logs),
      'service starts and stops cleanly')
check(any('showing Skip Intro at 5.0 s' in m for m in logs),
      'service started mid-episode looks it up and shows the button')
check(not any(level == xbmc.LOGERROR for level, _ in xbmc.LOG), 'no errors logged by the service loop')

SERVER.shutdown()
failed = [what for ok, what in RESULTS if not ok]
print('\n%d checks, %d failed' % (len(RESULTS), len(failed)))
sys.exit(1 if failed else 0)
