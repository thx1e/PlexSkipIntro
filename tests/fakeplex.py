"""Minimal fake Plex Media Server: just the endpoints the add-on (via plexapi 4.8) calls."""
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import quoteattr

TOKEN = 'GOODTOKEN'
SLOW = {'allLeaves': 0.0}   # seconds to delay allLeaves replies (stale-lookup test)
REQUESTS = []

SECTIONS = [
    {'key': '1', 'type': 'show', 'title': 'TV Shows', 'path': '/mnt/media/tv'},
    {'key': '2', 'type': 'show', 'title': 'ETV', 'path': '/mnt/media/etv'},
    {'key': '3', 'type': 'movie', 'title': 'Movies', 'path': '/mnt/media/movies'},
    {'key': '4', 'type': 'show', 'title': 'Anime', 'path': '/mnt/media/anime'},
]
SHOWS = [
    {'ratingKey': '100', 'section': '1', 'title': 'South Park'},
    {'ratingKey': '200', 'section': '2', 'title': 'South Park'},
    {'ratingKey': '300', 'section': '1', 'title': 'The Office (US)'},
    {'ratingKey': '301', 'section': '4', 'title': 'The Office (UK)'},
    {'ratingKey': '400', 'section': '1', 'title': 'Doctor Who'},
    {'ratingKey': '500', 'section': '1', 'title': 'Rick and Morty'},
]
# Movies (section 3). Endgame has a mid-credits scene between two credits markers.
MOVIES = [
    {'ratingKey': '9001', 'title': 'Inception', 'year': 2010,
     'file': '/mnt/media/movies/Inception (2010)/Inception (2010).mkv',
     'markers': [('credits', 8460000, 8880000, True)]},
    {'ratingKey': '9002', 'title': 'Avengers: Endgame', 'year': 2019,
     'file': '/mnt/media/movies/Avengers Endgame (2019)/Avengers Endgame (2019).mkv',
     'markers': [('credits', 10200000, 10500000, False), ('credits', 10560000, 10850000, True)]},
    {'ratingKey': '9003', 'title': 'Dune', 'year': 1984,
     'file': '/mnt/media/movies/Dune (1984)/Dune (1984).mkv', 'markers': []},
    {'ratingKey': '9004', 'title': 'Dune', 'year': 2021,
     'file': '/mnt/media/movies/Dune (2021)/Dune (2021).mkv',
     'markers': [('credits', 9000000, 9300000, True)]},
    {'ratingKey': '9005', 'title': "Le Fabuleux Destin d'Amélie Poulain", 'year': 2001,
     'file': '/mnt/media/movies/Amelie (2001)/Amelie (2001).mkv',
     'markers': [('credits', 7000000, 7300000, True)]},
    {'ratingKey': '9006', 'title': 'Intouchables', 'year': 2011,
     'file': '/mnt/media/movies/Intouchables (2011)/Intouchables (2011).mkv',
     'markers': [('credits', 6300000, 6600000, True)]},
]
EPISODES = [
    {'ratingKey': '1001', 'show': '100', 'season': 29, 'index': 1,
     'file': '/mnt/media/tv/South Park/Season 29/South Park - S29E01 - Episode One.mkv',
     'markers': [('intro', 5000, 36000, False), ('credits', 1290000, 1320000, True)]},
    {'ratingKey': '1002', 'show': '100', 'season': 29, 'index': 2,
     'file': '/mnt/media/tv/South Park/Season 29/South Park - S29E02 - Episode Two.mkv',
     'markers': [('commercial', 0, 1000, False), ('intro', 4000, 35000, False),
                 ('credits', 1295000, 1321000, True)]},
    {'ratingKey': '1003', 'show': '100', 'season': 27, 'index': 1,
     'file': '/mnt/media/tv/South Park/Season 27/South Park - S27E01 - Sermon.mkv', 'markers': []},
    {'ratingKey': '2005', 'show': '200', 'season': 10, 'index': 5,
     'file': '/mnt/media/etv/South Park/Season 10/South Park - S10E05 - Fat Camp.mkv', 'markers': []},
    {'ratingKey': '2902', 'show': '200', 'season': 29, 'index': 2,
     'file': '/mnt/media/etv/South Park/Season 29/South.Park.S29E02.1080p.WEB.mkv', 'markers': []},
    {'ratingKey': '3001', 'show': '300', 'season': 2, 'index': 1,
     'file': '/mnt/media/tv/The Office (US)/Season 02/The Office (US) - S02E01.mkv',
     'markers': [('intro', 60000, 90000, False)]},
    {'ratingKey': '3011', 'show': '301', 'season': 2, 'index': 1,
     'file': '/mnt/media/anime/The Office (UK)/Season 02/The Office (UK) - S02E01.mkv', 'markers': []},
    {'ratingKey': '4001', 'show': '400', 'season': 1, 'index': 1,
     'file': '/mnt/media/tv/Doctor Who (2005)/Season 01/Doctor Who (2005) - S01E01 - Rose.mkv',
     'markers': [('intro', 120000, 150000, False)]},
    # credits end at 21:10, post-credits scene runs to the end of the file (22:00); worst case: marked final
    {'ratingKey': '5001', 'show': '500', 'season': 7, 'index': 1,
     'file': '/mnt/media/tv/Rick and Morty/Season 07/Rick and Morty - S07E01.mkv',
     'markers': [('intro', 150000, 182000, False), ('credits', 1230000, 1270000, True)]},
]


def _movie_xml(movie, with_markers):
    markers = ''
    if with_markers:
        for i, (kind, start, end, final) in enumerate(movie['markers']):
            extra = ' final="1"' if final else ''
            markers += '<Marker id="%d" type="%s" startTimeOffset="%d" endTimeOffset="%d"%s/>' % (
                70 + i, kind, start, end, extra)
    return '<Video %s><Media id="%s"><Part %s/></Media>%s</Video>' % (
        _attrs(ratingKey=movie['ratingKey'], key='/library/metadata/%s' % movie['ratingKey'], type='movie',
               title=movie['title'], year=movie['year'], librarySectionID=3, duration=9000000, addedAt=1700000000),
        movie['ratingKey'],
        _attrs(id=movie['ratingKey'], key='/library/parts/%s/file.mkv' % movie['ratingKey'], file=movie['file'],
               duration=9000000, size=123456),
        markers)


def _attrs(**kw):
    return ' '.join('%s=%s' % (k, quoteattr(str(v))) for k, v in kw.items())


def _episode_xml(ep, with_markers):
    show = next(s for s in SHOWS if s['ratingKey'] == ep['show'])
    markers = ''
    if with_markers:
        for i, (kind, start, end, final) in enumerate(ep['markers']):
            extra = ' final="1"' if final else ''
            markers += '<Marker id="%d" type="%s" startTimeOffset="%d" endTimeOffset="%d"%s>' \
                       '<Attributes id="%d" version="5"/></Marker>' % (50 + i, kind, start, end, extra, 50 + i)
    return ('<Video %s><Media id="%s" duration="1330000" videoCodec="h264"><Part %s/></Media>%s</Video>' % (
        _attrs(ratingKey=ep['ratingKey'], key='/library/metadata/%s' % ep['ratingKey'],
               parentRatingKey='%s%02d' % (ep['show'], ep['season']), grandparentRatingKey=ep['show'],
               type='episode', title='Episode %s' % ep['index'], grandparentTitle=show['title'],
               parentIndex=ep['season'], index=ep['index'], duration=1330000,
               librarySectionID=show['section'], addedAt=1700000000),
        ep['ratingKey'],
        _attrs(id=ep['ratingKey'], key='/library/parts/%s/file.mkv' % ep['ratingKey'], file=ep['file'],
               duration=1330000, size=123456),
        markers))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body=''):
        data = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/xml;charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        token = self.headers.get('X-Plex-Token') or query.get('X-Plex-Token')
        REQUESTS.append(url.path + ('?' + url.query if url.query else ''))
        if token != TOKEN:
            return self._send(401, '<html><head><title>Unauthorized</title></head><body><h1>401 Unauthorized</h1></body></html>')
        path = url.path.rstrip('/') or '/'
        if path == '/':
            return self._send(200, '<MediaContainer size="0" friendlyName="fake-plex" machineIdentifier="abc123" '
                                   'version="1.42.1.10060" platform="Linux" myPlexUsername="a"/>')
        if path == '/library':
            return self._send(200, '<MediaContainer size="1" identifier="com.plexapp.plugins.library" '
                                   'title1="Plex Library"><Directory key="sections" title="Library Sections"/>'
                                   '</MediaContainer>')
        if path == '/library/sections':
            dirs = ''.join('<Directory %s><Location id="%s" path="%s"/></Directory>' % (
                _attrs(allowSync=1, key=s['key'], type=s['type'], title=s['title'], agent='tv.plex.agents.series',
                       scanner='Plex TV Series', language='en-US', uuid='uuid-%s' % s['key'],
                       updatedAt=1700000000, createdAt=1600000000, scannedAt=1700000000, content=1,
                       directory=1, contentChangedAt=1, hidden=0),
                s['key'], s['path']) for s in SECTIONS)
            return self._send(200, '<MediaContainer size="%d" title1="Plex Library">%s</MediaContainer>'
                              % (len(SECTIONS), dirs))
        m = re.match(r'^/library/sections/(\d+)/all$', path)
        if m and m.group(1) == '3':
            title = (query.get('title') or '').lower()
            year = query.get('year')
            hits = [mv for mv in MOVIES if title in mv['title'].lower() and (not year or str(mv['year']) == year)]
            body = ''.join(_movie_xml(mv, with_markers=False) for mv in hits)
            return self._send(200, '<MediaContainer size="%d" totalSize="%d" offset="0" librarySectionID="3">%s'
                                   '</MediaContainer>' % (len(hits), len(hits), body))
        if m:
            section = m.group(1)
            title = (query.get('title') or '').lower()
            hits = [s for s in SHOWS if s['section'] == section and title in s['title'].lower()]
            start = int(query.get('X-Plex-Container-Start', 0))
            size = int(query.get('X-Plex-Container-Size', 100))
            page = hits[start:start + size]
            body = ''.join('<Directory %s/>' % _attrs(
                ratingKey=s['ratingKey'], key='/library/metadata/%s/children' % s['ratingKey'],
                guid='plex://show/%s' % s['ratingKey'], type='show', title=s['title'],
                librarySectionID=section, index=1, addedAt=1600000000) for s in page)
            return self._send(200, '<MediaContainer size="%d" totalSize="%d" offset="%d" librarySectionID="%s">%s'
                                   '</MediaContainer>' % (len(page), len(hits), start, section, body))
        m = re.match(r'^/library/metadata/(\d+)/allLeaves$', path)
        if m:
            if SLOW['allLeaves']:
                time.sleep(SLOW['allLeaves'])
            eps = [e for e in EPISODES if e['show'] == m.group(1)]
            body = ''.join(_episode_xml(e, with_markers=False) for e in eps)
            return self._send(200, '<MediaContainer size="%d">%s</MediaContainer>' % (len(eps), body))
        m = re.match(r'^/library/metadata/(\d+)$', path)
        if m:
            with_markers = query.get('includeMarkers') == '1'
            ep = next((e for e in EPISODES if e['ratingKey'] == m.group(1)), None)
            if ep is not None:
                return self._send(200, '<MediaContainer size="1">%s</MediaContainer>' % _episode_xml(ep, with_markers))
            movie = next((mv for mv in MOVIES if mv['ratingKey'] == m.group(1)), None)
            if movie is not None:
                return self._send(200, '<MediaContainer size="1">%s</MediaContainer>' % _movie_xml(movie, with_markers))
            return self._send(404, '')
        return self._send(404, '')


def start():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:%d' % server.server_address[1]
