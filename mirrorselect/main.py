#!/usr/bin/env python
#-*- coding:utf-8 -*-


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


from __future__ import print_function


import os
import re
import shlex
import shutil
import socket
import string
import sys
from optparse import OptionParser
from mirrorselect.mirrorparser3 import MIRRORS_3_XML, MIRRORS_RSYNC_DATA
from mirrorselect.output import Output, ColoredFormatter
from mirrorselect.selectors import Deep, Shallow, Extractor, Interactive
from mirrorselect.version import version

# eprefix compatibility
try:
	from portage.const import rootuid
except ImportError:
	rootuid = 0


# establish the eprefix, initially set so eprefixify can
# set it on install
EPREFIX = "@GENTOO_PORTAGE_EPREFIX@"

# check and set it if it wasn't
if "GENTOO_PORTAGE_EPREFIX" in EPREFIX:
    EPREFIX = ''


if sys.hexversion >= 0x3000000:
    _unicode = str
else:
    _unicode = unicode


class MirrorSelect(object):
	'''Main operational class'''

	def __init__(self, output=None):
		'''MirrorSelect class init

		@param output: mirrorselect.output.Ouptut() class instance
			or None for the default instance
		'''
		self.output = output or Output()


	@staticmethod
	def _have_bin(name):
		"""Determines whether a particular binary is available
		on the host system.  It searches in the PATH environment
		variable paths.

		@param name: string, binary name to search for
		@rtype: string or None
		"""
		for path_dir in os.environ.get("PATH", "").split(":"):
			if not path_dir:
				continue
			file_path = os.path.join(path_dir, name)
			if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
				return file_path
		return None


	def write_config(self, hosts, out, config_path, sync=False):
		"""Writes the make.conf style string to the given file, or to stdout.

		@param hosts: list of host urls to write
		@param out: boolean, used to redirect output to stdout
		@param config_path; string
		@param sync: boolean, used to switch between SYNC and GENTOO_MIRRORS
			make.conf variable target
		"""
		if sync:
			var = 'SYNC'
		else:
			var = 'GENTOO_MIRRORS'

		if hasattr(hosts[0], 'decode'):
			hosts = [x.decode('utf-8') for x in hosts]

		mirror_string = '%s="%s"' % (var, ' '.join(hosts))

		if out:
			print()
			print(mirror_string)
			sys.exit(0)

		self.output.write('\n')
		self.output.print_info('Modifying %s with new mirrors...\n' % config_path)
		try:
			config = open(config_path, 'r')
			self.output.write('\tReading make.conf\n')
			lines = config.readlines()
			config.close()
			self.output.write('\tMoving to %s.backup\n' % config_path)
			shutil.move(config_path, config_path + '.backup')
		except IOError:
			lines = []

		regex = re.compile('^%s=.*' % var)
		for line in lines:
			if regex.match(line):
				lines.remove(line)

		lines.append(mirror_string)

		self.output.write('\tWriting new %s\n' % config_path)

		config = open(config_path, 'w')

		for line in lines:
			config.write(line)
		config.write('\n')
		config.close()

		self.output.print_info('Done.\n')
		sys.exit(0)


	def get_filesystem_mirrors(self, config_path, sync=False):
		"""Read the current mirrors and retain mounted filesystems mirrors

		@param config_path: string
		@param sync: boolean, used to switch between SYNC and GENTOO_MIRRORS
			make.conf variable target
		@rtype list
		"""
		fsmirrors = []

		if sync:
			var = 'SYNC'
		else:
			var = 'GENTOO_MIRRORS'

		self.output.write('get_filesystem_mirrors(): config_path = %s\n' % config_path, 2)
		try:
			f = open(config_path,'r')
		except IOError:
			return fsmirrors

		""" Search for 'var' in make.conf and extract value """
		try:
			lex = shlex.shlex(f, posix=True)
			lex.wordchars = string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"
			lex.quotes = "\"'"
			while 1:
				key = lex.get_token()
				#self.output.write('get_filesystem_mirrors(): processing key = %s\n' % key, 2)

				if key == var:
					equ = lex.get_token()

					if (equ == ''):
						break
					elif (equ != '='):
						break

					val = lex.get_token()
					if val is None:
						break

					""" Look for mounted filesystem in value """
					mirrorlist = val.rsplit()
					self.output.write('get_filesystem_mirrors(): mirrorlist = %s\n' % mirrorlist, 2)
					p = re.compile('rsync://|http://|ftp://', re.IGNORECASE)
					for mirror in mirrorlist:
						if (p.match(mirror) == None):
							if os.access(mirror, os.F_OK):
								self.output.write('get_filesystem_mirrors(): found file system mirror = %s\n' % mirror, 2)
								fsmirrors.append(mirror)
							else:
								self.output.write('get_filesystem_mirrors(): ignoring non-accessible mirror = %s\n' % mirror, 2)
					break
				elif key is None:
					break
		except Exception:
			fsmirrors = []

		self.output.write('get_filesystem_mirrors(): fsmirrors = %s\n' % fsmirrors, 2)
		return fsmirrors


	def _parse_args(self, argv, config_path):
		"""
		Does argument parsing and some sanity checks.
		Returns an optparse Options object.

		The descriptions, grouping, and possibly the amount sanity checking
		need some finishing touches.
		"""
		desc = "\n".join((
				self.output.white("examples:"),
				"",
				self.output.white("	 automatic:"),
				"		 # mirrorselect -s5",
				"		 # mirrorselect -s3 -b10 -o >> /mnt/gentoo/etc/portage/make.conf",
				"		 # mirrorselect -D -s4",
				"",
				self.output.white("	 interactive:"),
				"		 # mirrorselect -i -r",
				))
		parser = OptionParser(
			formatter=ColoredFormatter(self.output), description=desc,
			version='Mirrorselect version: %s' % version)

		group = parser.add_option_group("Main modes")
		group.add_option(
			"-i", "--interactive", action="store_true", default=False,
			help="Interactive Mode, this will present a list "
			"to make it possible to select mirrors you wish to use.")
		group.add_option(
			"-D", "--deep", action="store_true", default=False,
			help="Deep mode. This is used to give a more accurate "
			"speed test. It will download a 100k file from "
			"each server. Because of this you should only use "
			"this option if you have a good connection.")

		group = parser.add_option_group(
			"Server type selection (choose at most one)")
		group.add_option(
			"-F", "--ftp", action="store_true", default=False,
			help="ftp only mode. Will not consider hosts of other "
			"types.")
		group.add_option(
			"-H", "--http", action="store_true", default=False,
			help="http only mode. Will not consider hosts of other types")
		group.add_option(
			"-r", "--rsync", action="store_true", default=False,
			help="rsync mode. Allows you to interactively select your"
			" rsync mirror. Requires -i to be used.")
		group.add_option(
			"-4", "--ipv4", action="store_true", default=False,
			help="only use IPv4")
		group.add_option(
			"-6", "--ipv6", action="store_true", default=False,
			help="only use IPv6")
		group.add_option(
			"-c", "--country", action="store", default=None,
			help="only use mirrors from the specified country "
			"NOTE: Names with a space must be quoted "
			"eg.:  -c 'South Korea'")
		group.add_option(
			"-R", "--region", action="store", default=None,
			help="only use mirrors from the specified region"
			"NOTE: Names with a space must be quoted"
			"eg.:  -r 'North America'")

		group = parser.add_option_group("Other options")
		group.add_option(
			"-o", "--output", action="store_true", default=False,
			help="Output Only Mode, this is especially useful "
			"when being used during installation, to redirect "
			"output to a file other than %s" % config_path)
		group.add_option(
			"-b", "--blocksize", action="store", type="int",
			help="This is to be used in automatic mode "
			"and will split the hosts into blocks of BLOCKSIZE for "
			"use with netselect. This is required for certain "
			"routers which block 40+ requests at any given time. "
			"Recommended parameters to pass are: -s3 -b10")
		group.add_option(
			"-t", "--timeout", action="store", type="int",
			default="10", help="Timeout for deep mode. Defaults to 10 seconds.")
		group.add_option(
			"-s", "--servers", action="store", type="int", default=1,
			help="Specify Number of servers for Automatic Mode "
			"to select. this is only valid for download mirrors. "
			"If this is not specified, a default of 1 is used.")
		group.add_option(
			"-d", "--debug", action="store_const", const=2, dest="verbosity",
			default=1, help="debug mode")
		group.add_option(
			"-q", "--quiet", action="store_const", const=0, dest="verbosity",
			help="Quiet mode")

		if len(argv) == 1:
			parser.print_help()
			sys.exit(1)

		options, args = parser.parse_args(argv[1:])

		# sanity checks

		# hack: check if more than one of these is set
		if options.http + options.ftp + options.rsync > 1:
			self.output.print_err('Choose at most one of -H, -f and -r')

		if options.ipv4 and options.ipv6:
			self.output.print_err('Choose at most one of --ipv4 and --ipv6')

		if (options.ipv6 and not socket.has_ipv6) and not options.interactive:
			options.ipv6 = False
			self.output.print_err('The --ipv6 option requires python ipv6 support')

		if options.rsync and not options.interactive:
			self.output.print_err('rsync servers can only be selected with -i')

		if options.interactive and (
			options.deep or
			options.blocksize or
			options.servers > 1):
			self.output.print_err('Invalid option combination with -i')

		if (not options.deep) and (not self._have_bin('netselect') ):
			self.output.print_err(
				'You do not appear to have netselect on your system. '
				'You must use the -D flag')

		if (os.getuid() != rootuid) and not options.output:
			self.output.print_err('Must be root to write to %s!\n' % config_path)

		if args:
			self.output.print_err('Unexpected arguments passed.')

		# return results
		return options


	def get_available_hosts(self, options):
		'''Returns a list of hosts suitable for consideration by a user
		based on user input

		@param options: parser.parse_args() options instance
		@rtype: list
		'''
		if options.rsync:
			hosts = Extractor(MIRRORS_RSYNC_DATA, options, self.output).hosts
		else:
			hosts = Extractor(MIRRORS_3_XML, options, self.output).hosts
		return hosts


	def select_urls(self, hosts, options):
		'''Returns the list of selected host urls using
		the options passed in to run one of the three selector types.
		1) Interactive ncurses dialog
		2) Deep mode mirror selection.
		3) (Shallow) Rapid server selection via netselect

		@param hosts: list of hosts to choose from
		@param options: parser.parse_args() options instance
		@rtype: list
		'''
		if options.interactive:
			selector = Interactive(hosts, options, self.output)
		elif options.deep:
			selector = Deep(hosts, options, self.output)
		else:
			selector = Shallow(hosts, options, self.output)
		return selector.urls


	@staticmethod
	def get_make_conf_path():
		'''Checks for the existance of make.conf in /etc/portage/
		Failing that it checks for it in /etc/
		Failing in /etc/ it defaults to /etc/portage/make.conf

		@rtype: string
		'''
		# start with the new location
		config_path = EPREFIX + '/etc/portage/make.conf'
		if not os.access(config_path, os.F_OK):
			# check if the old location is what is used
			if os.access(EPREFIX + '/etc/make.conf', os.F_OK):
				config_path = EPREFIX + '/etc/make.conf'
		return config_path


	def main(self, argv):
		"""Lets Rock!

		@param argv: list of command line arguments to parse
		"""
		config_path = self.get_make_conf_path()

		options = self._parse_args(argv, config_path)
		self.output.verbosity = options.verbosity

		fsmirrors = self.get_filesystem_mirrors(config_path, options.rsync)

		hosts = self.get_available_hosts(options)

		urls = self.select_urls(hosts, options)

		self.write_config(fsmirrors + urls, options.output,
			config_path, options.rsync)

