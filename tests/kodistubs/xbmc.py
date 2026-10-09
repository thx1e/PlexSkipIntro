"""Stub of Kodi's xbmc module: just what the add-on uses, with controllable player state."""
LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3
LOG = []
COND = {}


def log(msg, level=LOGINFO):
    LOG.append((level, msg))


def getCondVisibility(condition):
    return COND.get(condition, False)


def getInfoLabel(label):
    return '21.2' if label == 'System.BuildVersion' else ''


class InfoTagVideo(object):
    def __init__(self, title='', season=-1, episode=-1, mediatype='', movie_title='', year=0, original=''):
        self.title, self.season, self.episode, self.mediatype = title, season, episode, mediatype
        self.movie_title, self.year, self.original = movie_title, year, original

    def getTVShowTitle(self):
        return self.title

    def getTitle(self):
        return self.movie_title

    def getYear(self):
        return self.year

    def getOriginalTitle(self):
        return self.original

    def getSeason(self):
        return self.season

    def getEpisode(self):
        return self.episode

    def getMediaType(self):
        return self.mediatype


class _State(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.playing = False
        self.time = 0.0
        self.total = 0.0
        self.file = ''
        self.tag = InfoTagVideo()
        self.seeks = []


STATE = _State()


class Player(object):
    def isPlayingVideo(self):
        return STATE.playing

    def isPlaying(self):
        return STATE.playing

    def getTime(self):
        return STATE.time

    def getTotalTime(self):
        return STATE.total

    def getPlayingFile(self):
        return STATE.file

    def getVideoInfoTag(self):
        return STATE.tag

    def seekTime(self, seconds):
        STATE.seeks.append(seconds)
        STATE.time = seconds


class Monitor(object):
    def __init__(self, *args, **kwargs):
        self._abort = False

    def abortRequested(self):
        return self._abort

    def waitForAbort(self, timeout=0):
        return self._abort
