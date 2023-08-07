#!/usr/bin/env python3

"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2009-2023 Gentoo Authors

	Copyright (C) 2009 Sebastian Pipping <sebastian@pipping.org>
	Copyright (C) 2009 Christian Ruppert <idl0r@gentoo.org>
	Copyright (C) 2012 Brian Dolbec <dolsen@gentoo.org>

Distributed under the terms of the GNU General Public License v2
 This program is free software; you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, version 2 of the License.

 This program is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

"""


from xml.etree import ElementTree as ET

MIRRORS_3_XML = "https://api.gentoo.org/mirrors/distfiles.xml"
MIRRORS_RSYNC_DATA = "https://api.gentoo.org/mirrors/rsync.xml"


class MirrorParser3:
    def __init__(self, options=None):
        self._reset()

    def _reset(self):
        self._dict = {}

    def _get_proto(self, uri=None):
        if not uri:  # Don't parse if empty
            return None
        try:
            from urllib.parse import urlparse

            return urlparse(uri).scheme
        except Exception as e:  # Add general exception to catch errors
            from mirrorselect.output import Output

            Output.write(
                (
                    "_get_proto(): Exception while parsing the protocol "
                    "for URI %s: %s\n"
                )
                % (uri, e),
                2,
            )

    def parse(self, text):
        self._reset()
        for mirrorgroup in ET.XML(text):
            for mirror in mirrorgroup:
                name = ""
                for e in mirror:
                    if e.tag == "name":
                        name = e.text
                    if e.tag == "uri":
                        uri = e.text
                        self._dict[uri] = {
                            "name": name,
                            "country": mirrorgroup.get("countryname"),
                            "region": mirrorgroup.get("region"),
                            "ipv4": e.get("ipv4"),
                            "ipv6": e.get("ipv6"),
                            "proto": e.get("protocol") or self._get_proto(uri),
                        }

    def tuples(self):
        return [(url, args) for url, args in list(self._dict.items())]

    def uris(self):
        return [url for url, args in list(self._dict.items())]


if __name__ == "__main__":
    import sys
    import urllib.request, urllib.parse, urllib.error

    parser = MirrorParser3()
    parser.parse(urllib.request.urlopen(MIRRORS_3_XML).read())
    print("===== tuples")
    print(parser.tuples())
    print("===== uris")
    print(parser.uris())
