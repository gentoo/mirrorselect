#!/usr/bin/python
# coding: utf-8

"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2009-2012 Gentoo Foundation

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


from __future__ import print_function

from xml.etree import ElementTree as ET

MIRRORS_3_XML = 'http://www.gentoo.org/main/en/mirrors3.xml'
MIRRORS_RSYNC_DATA = 'http://www.gentoo.org/main/en/mirrors-rsync-data.xml'

class MirrorParser3:
	def __init__(self):
		self._reset()

	def _reset(self):
		self._dict = {}

	def parse(self, text):
		self._reset()
		for mirrorgroup in ET.XML(text):
			for mirror in mirrorgroup:
				name = ''
				for e in mirror:
					if e.tag == 'name':
						name = e.text
					if e.tag == 'uri':
						uri = e.text
						self._dict[uri] = {
							"name": name,
							"country": mirrorgroup.get("countryname"),
							"region": mirrorgroup.get("region"),
							"ipv4": e.get("ipv4"),
							"ipv6": e.get("ipv6"),
							"proto": e.get("protocol"),
							}

	def tuples(self):
		return [(url, args) for url, args in list(self._dict.items())]

	def uris(self):
		return [url for url, args in list(self._dict.items())]

if __name__ == '__main__':
	if int(sys.version[0]) == 3:
		import urllib.request, urllib.parse, urllib.error
		parser = MirrorParser3()
		parser.parse(urllib.request.urlopen(MIRRORS_3_XML).read())
	else:
		import urllib
		parser = MirrorParser3()
		parser.parse(urllib.urlopen(MIRRORS_3_XML).read())
	print('===== tuples')
	print(parser.tuples())
	print('===== uris')
	print(parser.uris())
