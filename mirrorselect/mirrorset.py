"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2026 Gentoo Foundation

	Copyright (C) 2005 Colin Kingsley <tercel@gentoo.org>
	Copyright (C) 2008 Zac Medico <zmedico@gentoo.org>
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

from collections import namedtuple

Endpoint = namedtuple('Endpoint', 'uri name country ipv4 ipv6')

class MirrorEndpoint:
    """An endpoint of a mirror."""
    def __init__(self, uri: str, ipv4: bool, ipv6: bool, protocol: str):
        self.ipv4: bool = ipv4
        self.ipv6: bool = ipv6
        self.uri: str = uri
        self.protocol: str = protocol


class Mirror:
    """A mirror site and its available procotol endpoints."""
    def __init__(self, name: str, endpoints: list[MirrorEndpoint]):
        self.endpoints: list[MirrorEndpoint] = endpoints
        self.name: str = name

    def preferred_endpoint(self, protocols: list[str]):
        if len(self.endpoints) == 0:
            return None
        for protocol in protocols:
            preferred = next((e for e in self.endpoints if e.protocol == protocol), None)
            if preferred is not None:
                return preferred
        return self.endpoints[0]


class MirrorGroup:
    """Represents the set of mirrors available in one country."""
    def __init__(self, mirrors: list[Mirror], country: str,
                 countryname: str, region: str):
        self.mirrors: list[Mirror] = mirrors;
        self.region: str = region
        self.country: str = country
        self.countryname: str = countryname


class MirrorSet:
    """A set of mirrors and methods for filtering."""
    def __init__(self, groups: list[MirrorGroup]):
        self._groups: list[MirrorGroup] = groups

    def preferring_protocols(self, protocols: list[str]):
        """
        Select preferred endpoints for each mirror.

        A mirror usually has multiple endpoints with different protcols
        available. Select one from the specified list, in decreasing
        order of preference. Returns the first enpoint if none exists.
        """
        groups: list[MirrorGroup] = []
        for group in self._groups:
            new_mirrors: list[Mirror] = []
            for mirror in group.mirrors:
                preferred = mirror.preferred_endpoint(protocols)
                if preferred is None:
                    break
                new_mirrors.append(Mirror(mirror.name, [preferred]))
            if len(new_mirrors):
                groups.append(MirrorGroup(new_mirrors, group.country,
                                          group.countryname, group.region))
        return MirrorSet(groups)

    def only_protocol(self, protocol: str):
        """Select enpoints matching the specified protocol."""
        groups: list[MirrorGroup] = []
        for group in self._groups:
            new_mirrors: list[Mirror] = []
            for mirror in group.mirrors:
                preferred = next((e for e in mirror.endpoints if protocol == protocol), None)
                if preferred is None:
                    break
                new_mirrors.append(Mirror(mirror.name, [preferred]))
            if len(new_mirrors):
                groups.append(MirrorGroup(new_mirrors, group.country,
                                          group.countryname, group.region))
        return MirrorSet(groups)

    def with_country(self, country: str):
        """Select mirrors in the specified country."""
        return MirrorSet([g for g in self._groups if g.countryname == country])

    def with_region(self, region: str):
        """Select mirrors in the specified region."""
        return MirrorSet([g for g in self._groups if g.region == region])

    def mirrors(self) -> list[Endpoint]:
        """Each mirror endpoint in the set."""
        return [
            Endpoint(uri=e.uri, name=m.name, country=g.countryname, ipv4=e.ipv4, ipv6=e.ipv6)
            for g in self._groups
            for m in g.mirrors
            for e in m.endpoints
        ]

