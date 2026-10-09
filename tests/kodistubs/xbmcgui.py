"""Stub of Kodi's xbmcgui: records notifications and dialogs."""
NOTIFICATIONS = []


class Dialog(object):
    def notification(self, heading, message, icon='', time=5000, sound=True):
        NOTIFICATIONS.append(message)


class Control(object):
    def __init__(self):
        self.label = None

    def setLabel(self, label):
        self.label = label


class Action(object):
    def __init__(self, action_id):
        self._id = action_id

    def getId(self):
        return self._id


class WindowXMLDialog(object):
    INSTANCES = []

    def __new__(cls, *args, **kwargs):
        # Kodi builds the window in __new__ from (xmlFilename, scriptPath, defaultSkin, defaultRes)
        if len(args) < 2:
            raise TypeError('WindowXMLDialog needs xmlFilename and scriptPath')
        obj = object.__new__(cls)
        obj._args = args
        obj._controls = {}
        obj.visible = False
        WindowXMLDialog.INSTANCES.append(obj)
        return obj

    def show(self):
        self.visible = True
        self.onInit()          # Kodi calls onInit once the window is up

    def close(self):
        self.visible = False

    def getControl(self, control_id):
        return self._controls.setdefault(control_id, Control())
