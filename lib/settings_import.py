# -*- coding: utf-8 -*-
"""Read another addon's saved settings (addon_data/<id>/settings.xml). No Kodi imports."""
import xml.etree.ElementTree as ElementTree


def parse_kodi_settings(text):
    """Return {setting id: value} from a Kodi settings.xml.

    Handles both the current format (<setting id="x">value</setting>) and the
    legacy one (<setting id="x" value="value" />).
    """
    values = {}
    if not text:
        return values
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return values
    for node in root.iter('setting'):
        setting_id = node.get('id')
        if not setting_id:
            continue
        value = node.get('value')
        if value is None:
            value = node.text or ''
        values[setting_id] = value.strip()
    return values
