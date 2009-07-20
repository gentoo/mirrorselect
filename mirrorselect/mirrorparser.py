# Mirrorselect 1.x
# Tool for selecting Gentoo source and rsync mirrors.
#
# Copyright (C) 2005 Colin Kingsley <tercel@gentoo.org>
# Copyright (C) 2008 Zac Medico <zmedico@gentoo.org>
# Copyright (C) 2009 Sebastian Pipping <sebastian@pipping.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

from HTMLParser import HTMLParser

MIRRORS_XML = 'http://www.gentoo.org/main/en/mirrors.xml?passthru=1'

class MirrorParser(HTMLParser):
	"""
	MirrorParser objects are fed an html input stream via the feed() method.
	After the instance is closed, the lines atribute contains an array with
	elements of the form: (url, description)
	"""

	def __init__(self):
		HTMLParser.__init__(self)

		self.lines = []
		self.line = []

		self.get_desc = False
		self.in_sect = False
		self.sect_good = False
		self.check_title = False

		self.sects = ('North America', 'South America', 'Europe', 'Australia',
				'Asia', 'Other Mirrors:', 'Partial Mirrors')

	def handle_starttag(self, tag, attrs):
		if tag == 'section':
			self.in_sect = True
		if (tag == 'title') and self.in_sect:
			self.check_title = True
		if (tag == 'uri') and self.sect_good: #This is a good one
			self.line.append(dict(attrs)['link']) #url
			self.get_desc = True #the next data block is the description

	def handle_data(self, data):
		if self.check_title and (data in self.sects):
			self.sect_good = True
		if self.get_desc:
			if data.endswith('*'):
				data = data.replace('*', '')
				data = '* ' + data
			self.line.append(data)
			self.get_desc = False

	def handle_endtag(self, tag):
		if tag == 'section':
			self.in_sect = False
			self.sect_good = False
		if (tag == 'uri') and (len(self.line) == 2):
			self.lines.append(tuple(self.line))
			self.line = []

	def tuples(self):
		return self.lines

	def uris(self):
		return [url for url, description in self.lines]

if __name__ == '__main__':
	import urllib
	parser = MirrorParser()
	try:
		parser.feed(urllib.urlopen(MIRRORS_XML).read())
	except EnvironmentError:
		pass
	parser.close()
	print '===== tuples'
	print parser.tuples()
	print '===== uris'
	print parser.uris()
