"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2012 Gentoo Foundation

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

import os

from mirrorselect.mirrorparser3 import MirrorParser3
from sslfetch.connections import Connector
from mirrorselect.version import version

USERAGENT = "Mirrorselect-" + version

class Extractor:
	"""The Extractor employs a MirrorParser3 object to get a list of valid
	mirrors, and then filters them. Only the mirrors that should be tested,
	based on user input are saved. They will be in the hosts attribute."""

	def __init__(self, list_url, options, output):
		self.output = output
		self.output.print_info('Using url: %s\n' % list_url)
		filters = {}
		for opt in ["country", "region"]:
			value = getattr(options, opt)
			if value is not None:
				filters[opt] = value
				self.output.print_info('Limiting test to "%s=%s" hosts. \n'
					%(opt, value))
		for opt in ["ftp", "http", "https"]:
			if getattr(options, opt):
				filters["proto"] = opt
				self.output.print_info('Limiting test to %s hosts. \n' % opt )

		self.proxies = {}

		for proxy in ['http_proxy', 'https_proxy']:
			prox = proxy.split('_')[0]
			if options.proxy and prox + ":" in options.proxy:
				self.proxies[prox] = options.proxy
			elif os.getenv(proxy):
				self.proxies[prox] = os.getenv(proxy)

		parser = MirrorParser3()
		self.hosts = []

		self.unfiltered_hosts = self.getlist(parser, list_url)

		self.hosts = self.filter_hosts(filters, self.unfiltered_hosts)

		self.output.write('Extractor(): fetched mirrors,'
				' %s hosts after filtering\n' % len(self.hosts), 2)


	@staticmethod
	def filter_hosts(filters, hosts):
		"""Filter the hosts to the criteria passed in
		Return the filtered list
		"""
		if not len(filters):
			return hosts
		filtered = []
		for uri, data in hosts:
			good = True
			for f in filters:
				if data[f] != filters[f]:
					good = False
					continue
			if good:
				filtered.append((uri, data))
		return filtered


	def getlist(self, parser, url):
		"""
		Uses the supplied parser to get a list of urls.
		Takes a parser object, url, and filering options.
		"""

		self.output.write('getlist(): fetching ' + url + '\n', 2)

		self.output.print_info('Downloading a list of mirrors...\n')

		# setup the ssl-fetch ouptut map
		connector_output = {
			'info':self.output.write,
			'debug': self.output.write,
			'error': self.output.print_err,
			'kwargs-info': {'level': 2},
			'kwargs-debug': {'level':2},
			'kwargs-error': {'level':0},
			}

		fetcher = Connector(connector_output, self.proxies, USERAGENT)
		success, mirrorlist, timestamp = fetcher.fetch_content(url, climit=60)
		parser.parse(mirrorlist)

		if (not mirrorlist) or len(parser.tuples()) == 0:
			self.output.print_err('Could not get mirror list. '
				'Check your internet connection.')

		self.output.write(' Got %d mirrors.\n' % len(parser.tuples()))

		return parser.tuples()


