# Plex TV Skip Intro & Credits (Kodi)

Kodi service add-on that shows a Netflix-style **Skip Intro** / **Skip Credits** button, using the intro and credits markers your Plex server detects.

Fork of [Plex TV Skip Intro](https://github.com/Darkmadda/PlexSkipIntro) by dinomight. It uses its own add-on ID (`service.plexskipintrocredits`), so it installs alongside the original. Disable the original afterwards, or you get two buttons.

## What's different from the original

- **Skip Credits** as well as Skip Intro, for TV episodes and movies, each with its own on/off switch.
- **Looks in every Plex TV library**, not only one named "TV Shows". If the same episode is in more than one library, the copy whose file name matches the file Kodi is playing wins; otherwise the copy that has markers.
- **Movies** are looked up in every Plex movie library by title or original title, with the year (+/- 1) keeping remakes apart. If Kodi shows a translated title that Plex doesn't know, movies from that year are checked for the file Kodi is playing.
- **Post-credits scenes keep playing.** Skip Credits jumps to the end of the credits marker, never to the end of the file. Plex ends a credits marker where the credits end, so a mid- or post-credits scene plays, and a later credits marker after it gets its own button.
- **Imports the Plex URL and token** from the original add-on whenever either is blank, so nothing has to be typed on the TV.
- **Optional on-screen lookup result** when an episode starts (for example `South Park S29E02 (TV Shows): intro 0:05-0:36`), so you can see what Plex returned without reading logs. Turn it off in the settings once everything works. Errors are always shown.
- The button is not offered in the last 2 seconds of a marker, and seeking back before the end of a marker offers it again.

## Install

1. In Kodi: Settings → Add-ons → Install from zip file → pick `service.plexskipintrocredits.zip`.
2. Settings → Add-ons → My add-ons → Services → Plex TV Skip Intro → Disable.
3. Play an episode that has markers in Plex.

## Settings

| Setting | Default |
|---|---|
| Plex Base Url | blank; imported from the original add-on if set there, otherwise e.g. `http://192.168.1.10:32400` |
| Authentication Token | imported from the original add-on if set there |
| Show lookup result when an episode starts | on |
| Show Skip Intro button / timeout | on / 10 s |
| Show Skip Credits button for TV episodes | on |
| Show Skip Credits button for movies | on |
| Credits button timeout | 10 s |

## How it finds what's playing

Only items from Kodi's library are looked up.

- Episodes: Kodi's show title, season and episode number are searched in every Plex library of type "show", so Kodi and Plex have to agree on the show title and episode numbering.
- Movies: Kodi's title, original title and year are searched in every Plex library of type "movie"; the file name settles ties.

## Logs

Every step is logged to `kodi.log` with the prefix `[service.plexskipintrocredits]`.

## Requirements

- Kodi 19 or newer
- Plex Pass on the Plex server's owner account (needed for intro and credits detection)
- A Plex token

## Development

`tests/` runs the add-on outside Kodi: the real code and the bundled plexapi talk to a small fake Plex server, with stand-ins for Kodi's modules. Run `python3 tests/test_addon.py` (needs `requests`).

The release zip holds the add-on files under one top folder named `service.plexskipintrocredits`, without `tests/` and `.idea/`.

## License

GPL-3.0, like the original.
