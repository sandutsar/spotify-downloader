"""
Module for formatting songs into strings.
Contains functions to create search queries and song titles
and file names.
"""

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import pykakasi
from rapidfuzz import fuzz
from slugify import slugify as py_slugify
from yt_dlp.utils import sanitize_filename

from spotdl.types.song import Song

__all__ = [
    "VARS",
    "JAP_REGEX",
    "DISALLOWED_REGEX",
    "create_song_title",
    "sanitize_string",
    "slugify",
    "format_query",
    "create_search_query",
    "create_file_name",
    "parse_duration",
    "to_ms",
    "restrict_filename",
    "ratio",
]

VARS = [
    "{title}",
    "{artists}",
    "{artist}",
    "{album}",
    "{album-artist}",
    "{genre}",
    "{disc-number}",
    "{disc-count}",
    "{duration}",
    "{year}",
    "{original-date}",
    "{track-number}",
    "{tracks-count}",
    "{isrc}",
    "{track-id}",
    "{publisher}",
    "{list-length}",
    "{list-position}",
    "{list-name}",
    "{output-ext}",
]

KKS = pykakasi.kakasi()

JAP_REGEX = re.compile(
    "[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uff9f\u4e00-\u9faf\u3400-\u4dbf]"
)

DISALLOWED_REGEX = re.compile(r"[^-a-zA-Z0-9\!\@\$]+")

logger = logging.getLogger(__name__)


def create_song_title(song_name: str, song_artists: List[str]) -> str:
    """
    Create the song title.

    ### Arguments
    - song_name: the name of the song
    - song_artists: the list of artists of the song

    ### Returns
    - the song title

    ### Notes
    - Example: "Artist1, Artist2 - Song Name"

    """

    joined_artists = ", ".join(song_artists)
    if len(song_artists) >= 1:
        return f"{joined_artists} - {song_name}"

    return song_name


def sanitize_string(string: str) -> str:
    """
    Sanitize the filename to be used in the file system.

    ### Arguments
    - string: the string to sanitize

    ### Returns
    - the sanitized string
    """

    output = string

    # this is windows specific (disallowed chars)
    output = "".join(char for char in output if char not in "/?\\*|<>")

    # double quotes (") and semi-colons (:) are also disallowed characters but we would
    # like to retain their equivalents, so they aren't removed in the prior loop
    output = output.replace('"', "'").replace(":", "-")

    return output


@lru_cache()
def slugify(string: str) -> str:
    """
    Slugify the string.

    ### Arguments
    - string: the string to slugify

    ### Returns
    - the slugified string
    """

    # Replace ambiguous characters
    if not JAP_REGEX.search(string):
        # If string doesn't have japanese characters
        # return early
        return py_slugify(string, regex_pattern=DISALLOWED_REGEX.pattern)

    # Workaround for japanese characters
    # because slugify incorrectly converts them
    # to latin characters
    normal_slug = py_slugify(
        string,
        regex_pattern=JAP_REGEX.pattern,
    )

    results = KKS.convert(normal_slug)

    result = ""
    for index, item in enumerate(results):
        result += item["hepburn"]
        if not (
            item["kana"] == item["hepburn"]
            or item["kana"] == item["hepburn"]
            or (
                item == results[-1]
                or results[index + 1]["kana"] == results[index + 1]["hepburn"]
            )
        ):
            result += "-"

    return py_slugify(result, regex_pattern=DISALLOWED_REGEX.pattern)


def format_query(
    song: Song,
    template: str,
    santitize: bool,
    file_extension: Optional[str] = None,
    short: bool = False,
) -> str:
    """
    Replace template variables with the actual values.

    ### Arguments
    - song: the song object
    - template: the template string
    - santitize: whether to sanitize the string
    - file_extension: the file extension to use
    - short: whether to use the short version of the template

    ### Returns
    - the formatted string
    """

    if "{output-ext}" in template and file_extension is None:
        raise ValueError("file_extension is None, but template contains {output-ext}")

    for key, val in [
        ("{list-length}", song.list_length),
        ("{list-position}", song.list_position),
        ("{list-name}", song.list_name),
    ]:
        if not (key in template and val is None):
            continue

        logger.warning(
            "Template contains %s, but it's value is None. Replacing with empty string.",
            key,
        )

        template = template.replace(key, "")
        template = template.replace(r"//", r"/")

    # If template has only {output-ext}, fix it
    if template in ["/.{output-ext}", ".{output-ext}"]:
        template = "{artists} - {title}.{output-ext}"

    # Remove artists from the list that are already in the title
    artists = [
        artist for artist in song.artists if slugify(artist) not in slugify(song.name)
    ]

    # Add the main artist again to the list
    if len(artists) == 0 or artists[0] != song.artists[0]:
        artists.insert(0, song.artists[0])

    artists_str = ", ".join(artists)

    # the code below is valid, song_list is actually checked for None
    formats = {
        "{title}": song.name,
        "{artists}": song.artists[0] if short is True else artists_str,
        "{artist}": song.artists[0],
        "{album}": song.album_name,
        "{album-artist}": song.album_artist,
        "{genre}": song.genres[0] if song.genres else "",
        "{disc-number}": song.disc_number,
        "{disc-count}": song.disc_count,
        "{duration}": song.duration,
        "{year}": song.year,
        "{original-date}": song.date,
        "{track-number}": f"{song.track_number:02d}",
        "{tracks-count}": song.tracks_count,
        "{isrc}": song.isrc,
        "{track-id}": song.song_id,
        "{publisher}": song.publisher,
        "{output-ext}": file_extension,
        "{list-name}": song.list_name,
        "{list-position}": str(song.list_position).zfill(len(str(song.list_length))),
        "{list-length}": song.list_length,
    }

    if santitize:
        # sanitize the values in formats dict
        for key, value in formats.items():
            if value is None:
                continue

            formats[key] = sanitize_string(str(value))

    # Replace all the keys with the values
    for key, value in formats.items():
        template = template.replace(key, str(value))

    return template


def create_search_query(
    song: Song,
    template: str,
    santitize: bool,
    file_extension: Optional[str] = None,
    short: bool = False,
) -> str:
    """
    Create the search query for the song.

    ### Arguments
    - song: the song object
    - template: the template string
    - santitize: whether to sanitize the string
    - file_extension: the file extension to use
    - short: whether to use the short version of the template

    ### Returns
    - the formatted string
    """

    # If template does not contain any of the keys,
    # append {artist} - {title} at the beggining of the template
    if not any(key in template for key in VARS):
        template = "{artist} - {title}" + template

    return format_query(song, template, santitize, file_extension, short=short)


def create_file_name(
    song: Song,
    template: str,
    file_extension: str,
    restrict: bool = False,
    short: bool = False,
) -> Path:
    """
    Create the file name for the song, by replacing template variables with the actual values.

    ### Arguments
    - song: the song object
    - template: the template string
    - file_extension: the file extension to use
    - restrict: whether to sanitize the filename
    - short: whether to use the short version of the template

    ### Returns
    - the formatted string as a Path object
    """

    # If template does not contain any of the keys,
    # append {artists} - {title}.{output-ext} to it
    if not any(key in template for key in VARS) and template != "":
        template += "/{artists} - {title}.{output-ext}"

    if template == "":
        template = "{artists} - {title}.{output-ext}"

    # If template ends with a slash. Does not have a file name with extension
    # at the end of the template, append {artists} - {title}.{output-ext} to it
    if template.endswith("/") or template.endswith(r"\\") or template.endswith("\\\\"):
        template += "/{artists} - {title}.{output-ext}"

    # If template does not end with {output-ext}, append it to the end of the template
    if not template.endswith(".{output-ext}"):
        template += ".{output-ext}"

    formatted_string = format_query(
        song=song,
        template=template,
        santitize=True,
        file_extension=file_extension,
        short=short,
    )

    # Parse template as Path object
    file = Path(formatted_string)

    santitized_parts = []
    for part in file.parts:
        match = re.search(r"[^\.*](.*)[^\.*$]", part)
        if match and part != ".spotdl":
            santitized_parts.append(match.group(0))
        else:
            santitized_parts.append(part)

    # Join the parts of the path
    file = Path(*santitized_parts)

    # Check if the file name length is greater than 255
    if len(file.name) < 255:
        # Restrict the filename if needed
        if restrict:
            return restrict_filename(file)

        return file

    # If the file name length is greater than 255,
    # and we are already using the short version of the template,
    # fallback to default template
    if short is True:
        # Path template is already short, but we still can't create a file
        # so we reduce it even further
        if template == "{artist} - {title}.{output-ext}":
            if len(song.name) > 240:
                logger.warning(
                    "%s: File name is too long. Using only part of the song title.",
                    song.display_name,
                )

                name_parts = song.name.split(" ")
                new_name = ""
                for part in name_parts:
                    if len(new_name) + len(part) < 240:
                        new_name += part + " "
                    else:
                        break

                song.name = new_name.strip()
            else:
                logger.warning(
                    "%s: File name is too long. Using only song title.",
                    song.display_name,
                )

            return create_file_name(
                song=song,
                template="{title}.{output-ext}",
                file_extension=file_extension,
                restrict=restrict,
                short=short,
            )

        # This will probably never occur, but just in case
        if template == "{title}.{output-ext}":
            raise RecursionError(
                f'"{song.display_name} is too long to be shortened. File a bug report on GitHub'
            )

        logger.warning(
            "%s: File name is too long. Using the default template.",
            song.display_name,
        )

        return create_file_name(
            song=song,
            template="{artist} - {title}.{output-ext}",
            file_extension=file_extension,
            restrict=restrict,
            short=short,
        )

    return create_file_name(
        song, template, file_extension, restrict=restrict, short=True
    )


def parse_duration(duration: Optional[str]) -> float:
    """
    Convert string value of time (duration: "25:36:59") to a float value of seconds (92219.0)

    ### Arguments
    - duration: the string value of time

    ### Returns
    - the float value of seconds
    """

    if duration is None:
        return 0.0

    try:
        # {(1, "s"), (60, "m"), (3600, "h")}
        mapped_increments = zip([1, 60, 3600], reversed(duration.split(":")))
        seconds = sum(multiplier * int(time) for multiplier, time in mapped_increments)
        return float(seconds)

    # This usually occurs when the wrong string is mistaken for the duration
    except (ValueError, TypeError, AttributeError):
        return 0.0


def to_ms(
    string: Optional[str] = None, precision: Optional[int] = None, **kwargs
) -> float:
    """
    Convert a string to milliseconds.

    ### Arguments
    - string: the string to convert
    - precision: the number of decimals to round to
    - kwargs: the keyword args to convert

    ### Returns
    - the milliseconds

    ### Notes
    - You can either pass a string,
    - or a set of keyword args ("hour", "min", "sec", "ms") to convert.
    - If "precision" is set, the result is rounded to the number of decimals given.
    - From: https://gist.github.com/Hellowlol/5f8545e999259b4371c91ac223409209
    """

    if string:
        hour = int(string[0:2])
        minute = int(string[3:5])
        sec = int(string[6:8])
        milliseconds = int(string[10:11])
    else:
        hour = int(kwargs.get("hour", 0))
        minute = int(kwargs.get("min", 0))
        sec = int(kwargs.get("sec", 0))
        milliseconds = int(kwargs.get("ms", 0))

    result = (
        (hour * 60 * 60 * 1000) + (minute * 60 * 1000) + (sec * 1000) + milliseconds
    )

    if precision and isinstance(precision, int):
        return round(result, precision)

    return result


def restrict_filename(pathobj: Path) -> Path:
    """
    Sanitizes the filename part of a Path object. Returns modified object.

    ### Arguments
    - pathobj: the Path object to sanitize

    ### Returns
    - the modified Path object

    ### Notes
    - Based on the `sanitize_filename` function from yt-dlp
    """

    result = sanitize_filename(pathobj.name, True, False)
    result = result.replace("_-_", "-")

    if not result:
        result = "_"

    return pathobj.with_name(result)


@lru_cache()
def ratio(string1: str, string2: str) -> float:
    """
    Wrapper for fuzz.ratio
    with lru_cache

    ### Arguments
    - string1: the first string
    - string2: the second string

    ### Returns
    - the ratio
    """

    return fuzz.ratio(string1, string2)
