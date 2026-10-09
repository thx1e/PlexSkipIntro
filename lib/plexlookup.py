# -*- coding: utf-8 -*-
"""Find the Plex item Kodi is playing and read its intro/credits markers.

No Kodi imports here, so this module can be tested outside Kodi.

TV episodes:
  1. every Plex library of type "show" (not just one named "TV Shows")
  2. shows whose title matches Kodi's show title (exact title preferred; a
     trailing "(year)" is retried without the year)
  3. the episode by season/episode number
  4. if more than one library has that episode, the copy whose file name is
     the file Kodi is playing wins; otherwise the copy that has markers.

Movies:
  1. every Plex library of type "movie"
  2. movies whose title matches Kodi's title or original title exactly, or
     whose file is the file Kodi is playing
  3. the file Kodi is playing wins; otherwise the year must match (+/- 1),
     which keeps remakes apart
  4. if the title is not found at all (e.g. Kodi shows a translated title),
     movies from that year are checked for the file Kodi is playing.
"""
import re

try:
    from urllib.parse import unquote
except ImportError:  # pragma: no cover - Python 2, never used by Kodi 19+
    from urllib import unquote

MARKER_TYPES = ('intro', 'credits')
MAX_FUZZY_SHOWS = 5  # when no exact show title matches, try at most this many "contains" matches
MAX_MOVIE_DETAILS = 3
_YEAR_SUFFIX = re.compile(r'\s*\((?:19|20)\d{2}\)\s*$')


def file_basename(path):
    """Lower-case file name from a Kodi or Plex path (smb://..., nfs://..., /mnt/..., C:\\...)."""
    if not path:
        return ''
    if '%' in path:
        path = unquote(path)
    name = re.split(r'[\\/]', path.rstrip('/\\'))[-1]
    return name.strip().lower()


def title_variants(title):
    """Titles to search for: as given, then without a trailing "(year)"."""
    title = (title or '').strip()
    variants = [title] if title else []
    bare = _YEAR_SUFFIX.sub('', title).strip()
    if bare and bare not in variants:
        variants.append(bare)
    return variants


def fmt_time(seconds):
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '%d:%02d:%02d' % (hours, minutes, secs)
    return '%d:%02d' % (minutes, secs)


class Marker(object):
    """An intro or credits range, in seconds."""

    def __init__(self, kind, start, end, final=False):
        self.kind = kind
        self.start = float(start)
        self.end = float(end)
        self.final = final
        self.shown = False

    def label(self):
        return '%s %s-%s' % (self.kind, fmt_time(self.start), fmt_time(self.end))

    def __repr__(self):
        return '<Marker %s>' % self.label()


class LookupResult(object):
    FOUND = 'found'          # item found; markers may still be empty
    NOT_FOUND = 'not_found'  # no library has this item
    ERROR = 'error'          # Plex unreachable, bad token, unexpected reply

    def __init__(self, status, markers=None, library='', title='', file_match=False, message=''):
        self.status = status
        self.markers = markers or []
        self.library = library
        self.title = title
        self.file_match = file_match
        self.message = message

    def summary(self, label, kind='episode'):
        """One line for the log and the on-screen notification."""
        if self.status == self.FOUND:
            where = '%s (%s)' % (label, self.library) if self.library else label
            if self.markers:
                return '%s: %s' % (where, ', '.join(m.label() for m in self.markers))
            wanted = 'intro/credits' if kind == 'episode' else 'credits'
            return '%s: no %s markers in Plex yet' % (where, wanted)
        if self.status == self.NOT_FOUND:
            library = 'TV' if kind == 'episode' else 'movie'
            return '%s: not found in any Plex %s library' % (label, library)
        return '%s: Plex error: %s' % (label, self.message)


def parse_markers(video):
    """Intro/credits markers from a Plex <Video> element, sorted by start time."""
    markers = []
    for node in video.iter('Marker'):
        kind = node.get('type')
        if kind not in MARKER_TYPES:
            continue
        try:
            start = int(node.get('startTimeOffset')) / 1000.0
            end = int(node.get('endTimeOffset')) / 1000.0
        except (TypeError, ValueError):
            continue
        if end > start:
            markers.append(Marker(kind, start, end, node.get('final') == '1'))
    markers.sort(key=lambda marker: marker.start)
    return markers


def _details(server, rating_key):
    """(file names, markers) of one Plex item, or None when Plex returns no <Video>."""
    data = server.query('/library/metadata/%s?includeMarkers=1' % rating_key)
    video = data.find('Video') if data is not None else None
    if video is None:
        return None
    return [file_basename(part.get('file')) for part in video.iter('Part')], parse_markers(video)


def _sections(server, kind):
    return [section for section in server.library.sections() if getattr(section, 'type', None) == kind]


# --- TV episodes ------------------------------------------------------------------------

def _episode_candidates(server, title, season, episode, log):
    """(library title, show, episode) for every TV library that has this episode."""
    found = []
    seen = set()
    wanted = [variant.lower() for variant in title_variants(title)]
    for section in _sections(server, 'show'):
        for variant in title_variants(title):
            try:
                shows = section.search(variant)
            except Exception as exc:
                log('search for %r in %r failed: %s' % (variant, section.title, exc))
                continue
            if not shows:
                continue
            exact = [show for show in shows if (show.title or '').strip().lower() in wanted]
            for show in exact or shows[:MAX_FUZZY_SHOWS]:
                if show.ratingKey in seen:
                    continue
                seen.add(show.ratingKey)
                try:
                    found.append((section.title, show, show.episode(None, season, episode)))
                except Exception:
                    pass  # this show has no such episode (plexapi raises NotFound)
            break  # the first title variant that matched shows in this library is enough
    return found


def find_episode(server, title, season, episode, playing_file, log=None):
    """Look up a TV episode on a plexapi PlexServer and return a LookupResult.

    Connection and authorization errors from the server propagate to the caller.
    """
    log = log or (lambda message: None)
    want = file_basename(playing_file)
    candidates = _episode_candidates(server, title, season, episode, log)
    if not candidates:
        return LookupResult(LookupResult.NOT_FOUND)

    wanted = [variant.lower() for variant in title_variants(title)]
    scored = []
    for library, show, ep in candidates:
        try:
            details = _details(server, ep.ratingKey)
        except Exception as exc:
            log('reading markers for item %s failed: %s' % (ep.ratingKey, exc))
            continue
        if details is None:
            continue
        files, markers = details
        file_match = bool(want) and want in files
        exact = (show.title or '').strip().lower() in wanted
        log('candidate %s / %s: file match=%s, markers=%s' % (library, show.title, file_match, markers or 'none'))
        scored.append(((file_match, bool(markers), exact),
                       LookupResult(LookupResult.FOUND, markers, library, show.title, file_match)))

    if not scored:
        return LookupResult(LookupResult.ERROR, message='could not read episode details')
    if any(score[0] for score, _ in scored):
        # The exact file Kodi is playing is authoritative, even without markers:
        # another copy (different release or cut) can have different timings.
        scored = [item for item in scored if item[0][0]]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


# --- movies -----------------------------------------------------------------------------

def _movie_files(movie):
    try:
        return [file_basename(part.file) for media in (movie.media or []) for part in media.parts]
    except Exception:
        return []


def _movies_by_year_and_file(server, sections, year, want, log):
    """Movies from `year` (+/- 1) whose file is the one Kodi is playing."""
    for section in sections:
        for candidate_year in (year, year - 1, year + 1):
            try:
                data = server.query('/library/sections/%s/all?type=1&year=%d' % (section.key, candidate_year))
            except Exception as exc:
                log('year search %d in %r failed: %s' % (candidate_year, section.title, exc))
                continue
            for video in (data.findall('Video') if data is not None else []):
                files = [file_basename(part.get('file')) for part in video.iter('Part')]
                if want in files:
                    year_attr = video.get('year')
                    return [(section.title, video.get('ratingKey'), video.get('title'),
                             int(year_attr) if year_attr and year_attr.isdigit() else candidate_year, files)]
    return []


def find_movie(server, title, original_title, year, playing_file, log=None):
    """Look up a movie on a plexapi PlexServer and return a LookupResult.

    Connection and authorization errors from the server propagate to the caller.
    """
    log = log or (lambda message: None)
    want = file_basename(playing_file)
    year = int(year or 0)
    titles = []
    for variant in title_variants(title) + title_variants(original_title):
        if variant.lower() not in [existing.lower() for existing in titles]:
            titles.append(variant)
    wanted = [variant.lower() for variant in titles]
    sections = _sections(server, 'movie')

    hits = []  # (library, ratingKey, title, year, file names)
    seen = set()
    for section in sections:
        for variant in titles:
            try:
                movies = section.search(variant)
            except Exception as exc:
                log('search for %r in %r failed: %s' % (variant, section.title, exc))
                continue
            for movie in movies:
                if movie.ratingKey in seen:
                    continue
                files = _movie_files(movie)
                exact = (movie.title or '').strip().lower() in wanted
                if not (exact or (want and want in files)):
                    continue  # a partial title match that is not this file
                seen.add(movie.ratingKey)
                hits.append((section.title, movie.ratingKey, movie.title, movie.year or 0, files))
    if not hits and year and want:
        hits = _movies_by_year_and_file(server, sections, year, want, log)

    file_hits = [hit for hit in hits if want and want in hit[4]]
    if file_hits:
        pool = file_hits[:1]  # the exact file Kodi is playing is authoritative
    else:
        pool = [hit for hit in hits if not year or not hit[3] or abs(hit[3] - year) <= 1]
        pool.sort(key=lambda hit: hit[3] == year, reverse=True)
        pool = pool[:MAX_MOVIE_DETAILS]
    if not pool:
        return LookupResult(LookupResult.NOT_FOUND)

    results = []
    for library, key, movie_title, movie_year, _ in pool:
        try:
            details = _details(server, key)
        except Exception as exc:
            log('reading markers for item %s failed: %s' % (key, exc))
            continue
        if details is None:
            continue
        files, markers = details
        log('candidate %s / %s (%s): markers=%s' % (library, movie_title, movie_year, markers or 'none'))
        results.append(LookupResult(LookupResult.FOUND, markers, library, movie_title, bool(want) and want in files))
    if not results:
        return LookupResult(LookupResult.ERROR, message='could not read movie details')
    with_markers = [result for result in results if result.markers]
    return (with_markers or results)[0]
