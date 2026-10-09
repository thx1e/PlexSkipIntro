"""Stub of Kodi's xbmcvfs: special://profile/ maps to a temp folder."""
import os

PROFILE = ''


def translatePath(path):
    return path.replace('special://profile/', PROFILE.rstrip('/') + '/')


def exists(path):
    return os.path.exists(translatePath(path))


class File(object):
    def __init__(self, path):
        self._handle = open(translatePath(path), encoding='utf-8')

    def read(self):
        return self._handle.read()

    def close(self):
        self._handle.close()
