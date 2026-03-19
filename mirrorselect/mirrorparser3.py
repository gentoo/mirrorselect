#!/usr/bin/env python3

"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2009-2026 Gentoo Authors

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
from mirrorselect.mirrorset import MirrorSet, MirrorGroup, MirrorEndpoint, Mirror

MIRRORS_3_XML = "https://api.gentoo.org/mirrors/distfiles.xml"
MIRRORS_RSYNC_DATA = "https://api.gentoo.org/mirrors/rsync.xml"

class MirrorParser3:
    @staticmethod
    def parse(text: str):
        groups: list[MirrorGroup] = []
        for group_element in ET.XML(text):
            mirrors: list[Mirror] = []
            region = group_element.get("region")
            country = group_element.get("country")
            countryname = group_element.get("countryname")
            if region is None:
                raise Exception("mirror has no region")
            if country is None:
                raise Exception("mirror has no country")
            if countryname is None:
                raise Exception("mirror has no countryname")

            for mirror_element in group_element:
                endpoints: list[MirrorEndpoint] = []
                mirror_name: str | None = None
                for element in mirror_element:
                    if element.tag == "name":
                        mirror_name = element.text
                    if element.tag == "uri":
                        ipv4 = element.get("ipv4") == "y"
                        ipv6 = element.get("ipv6") == "y"
                        uri = element.text
                        protocol = element.get("protocol")
                        if uri is None:
                            raise Exception("uri is missing")
                        if protocol is None:
                            raise Exception("protocol is missing")
                        endpoints.append(MirrorEndpoint(uri, ipv4, ipv6, protocol))
                if mirror_name is None:
                    raise Exception("name missing from mirror")
                mirrors.append(Mirror(mirror_name, endpoints))
            group = MirrorGroup(mirrors, country, countryname, region)
            groups.append(group)
        return MirrorSet(groups)

if __name__ == "__main__":
  import urllib.request
  mirrorset = MirrorParser3.parse(urllib.request.urlopen(MIRRORS_3_XML).read())
  print (len(mirrorset.uris()))
  mirrorset = mirrorset.preferring_protocols(["https", "http"])
  print (len(mirrorset.uris()))
  print (len(mirrorset.uris()))
  print(mirrorset.uris())

