"""Stub of Kodi's xbmcaddon: one shared settings dict seeded from the add-on's settings.xml defaults."""
import xml.etree.ElementTree as ET

SETTINGS = {}
INFO = {'version': '', 'id': 'service.plexskipintrocredits', 'path': ''}
TYPES = {}


def load_defaults(addon_dir):
    INFO['path'] = addon_dir
    INFO['version'] = ET.parse(addon_dir + '/addon.xml').getroot().get('version')
    SETTINGS.clear()
    for node in ET.parse(addon_dir + '/resources/settings.xml').getroot().iter('setting'):
        TYPES[node.get('id')] = node.get('type')
        SETTINGS[node.get('id')] = node.get('default', '')


class Addon(object):
    def __init__(self, id=None):
        pass

    def getAddonInfo(self, key):
        return INFO[key]

    def getSetting(self, key):
        return str(SETTINGS.get(key, ''))

    def getSettingString(self, key):
        if TYPES.get(key) != 'text':
            raise TypeError('%s is not a string setting' % key)
        return str(SETTINGS.get(key, ''))

    def getSettingBool(self, key):
        if TYPES.get(key) != 'bool':
            raise TypeError('%s is not a bool setting' % key)
        return str(SETTINGS[key]).lower() == 'true'

    def getSettingInt(self, key):
        if TYPES.get(key) != 'number':
            raise TypeError('%s is not a number setting' % key)
        return int(SETTINGS[key])

    def setSettingString(self, key, value):
        if TYPES.get(key) != 'text':
            raise TypeError('%s is not a string setting' % key)
        SETTINGS[key] = value

    def setSetting(self, key, value):
        SETTINGS[key] = value
