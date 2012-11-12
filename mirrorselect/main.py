#!/usr/bin/python

# Mirrorselect 2.x
# Tool for selecting Gentoo source and rsync mirrors.
#
# Copyright (C) 2005 Colin Kingsley <tercel@gentoo.org>
# Copyright (C) 2008 Zac Medico <zmedico@gentoo.org>
# Copyright (C) 2009 Sebastian Pipping <sebastian@pipping.org>
# Copyright (C) 2009 Christian Ruppert <idl0r@gentoo.org>
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

__revision__ = '2.1.0'

import os
import re
import shlex
import shutil
import socket
import string
import sys
from optparse import OptionParser
from mirrorselect.mirrorparser3 import MIRRORS_3_XML, MIRRORS_RSYNC_DATA
from mirrorselect.output import output, ColoredFormatter
from mirrorselect.selectors import Deep, Shallow, Extractor, Interactive


def _have_bin(name):
	"""
	Determines whether a particular binary is available on the host system.
	"""
	for path_dir in os.environ.get("PATH", "").split(":"):
		if not path_dir:
			continue
		file_path = os.path.join(path_dir, name)
		if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
			return file_path
	return None


def write_config(hosts, out, path, sync=False):
	"""
	Writes the make.conf style string to the given file, or to stdout.
	"""
	if sync:
		var = 'SYNC'
	else:
		var = 'GENTOO_MIRRORS'

	mirror_string = '%s="%s"' % (var, ' '.join(hosts))

	if out:
		print
		print mirror_string
		sys.exit(0)


	output.write('\n')
	output.print_info('Modifying %s with new mirrors...\n' % path)
	try:
		config = open(path, 'r')
		output.write('\tReading make.conf\n')
		lines = config.readlines()
		config.close()
		output.write('\tMoving to %s.backup\n' % path)
		shutil.move(path, path + '.backup')
	except IOError:
		lines = []

	regex = re.compile('^%s=.*' % var)
	for line in lines:
		if regex.match(line):
			lines.remove(line)

	lines.append(mirror_string)

	output.write('\tWriting new %s\n' % path)
	config = open(path, 'w')
	for line in lines:
		config.write(line)
	config.write('\n')
	config.close()

	output.print_info('Done.\n')
	sys.exit(0)

def get_filesystem_mirrors(out, path, sync=False):
	"""
	Read the current mirrors and retain mounted filesystems mirrors
	"""
	fsmirrors = []

	if sync:
		var = 'SYNC'
	else:
		var = 'GENTOO_MIRRORS'

	try:
		f = open(path,'r')
	except IOError:
		return fsmirrors

	""" Search for 'var' in make.conf and extract value """
	try:
		lex = shlex.shlex(f, posix=True)
		lex.wordchars = string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"
		lex.quotes = "\"'"
		while 1:
			key = lex.get_token()
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
				p = re.compile('rsync://|http://|ftp://', re.IGNORECASE)
				for mirror in mirrorlist:
					if (p.match(mirror) == None):
						fsmirrors.append(mirror)
				break
			elif key is None:
				break
	except Exception:
		fsmirrors = []

	return fsmirrors

def parse_args(argv, config_path):
	"""
	Does argument parsing and some sanity checks.
	Returns an optparse Options object.

	The descriptions, grouping, and possibly the amount sanity checking
	need some finishing touches.
	"""
	desc = "\n".join((
			output.white("examples:"),
			"",
			output.white("	 automatic:"),
			"		 # mirrorselect -s5",
			"		 # mirrorselect -s3 -b10 -o >> /mnt/gentoo/etc/portage/make.conf",
			"		 # mirrorselect -D -s4",
			"",
			output.white("	 interactive:"),
			"		 # mirrorselect -i -r",
			))
	parser = OptionParser(
		formatter=ColoredFormatter(), description=desc,
		version='Mirrorselect version: %s' % __revision__)

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
		output.print_err('Choose at most one of -H, -f and -r')

	if options.ipv4 and options.ipv6:
		output.print_err('Choose at most one of --ipv4 and --ipv6')

	if (options.ipv6 and not socket.has_ipv6) and not options.interactive:
		options.ipv6 = False
		output.print_err('The --ipv6 option requires python ipv6 support')

	if options.rsync and not options.interactive:
		output.print_err('rsync servers can only be selected with -i')

	if options.interactive and (
		options.deep or
		options.blocksize or
		options.servers > 1):
		output.print_err('Invalid option combination with -i')

	if (not options.deep) and (not _have_bin('netselect') ):
		output.print_err(
			'You do not appear to have netselect on your system. '
			'You must use the -D flag')

	if (os.getuid() != 0) and not options.output:
		output.print_err('Must be root to write to %s!\n' % config_path)

	if args:
		output.print_err('Unexpected arguments passed.')

	# return results
	return options


def main(argv):
	"""Lets Rock!"""
	# start with the new location
	config_path = '/etc/portage/make.conf'
	if not os.access(config_path, os.F_OK):
		# check if the old location is what is used
		if os.access('/etc/make.conf', os.F_OK):
			config_path = '/etc/make.conf'

	#output.print_info("config_path set to :", config_path)

	options = parse_args(argv, config_path)
	output.verbosity = options.verbosity

	fsmirrors = get_filesystem_mirrors(options.output, config_path, options.rsync)
	if options.rsync:
		hosts = Extractor(MIRRORS_RSYNC_DATA, options).hosts
	else:
		hosts = Extractor(MIRRORS_3_XML, options).hosts

	if options.interactive:
		selector = Interactive(hosts, options)
	elif options.deep:
		selector = Deep(hosts, options)
	else:
		selector = Shallow(hosts, options)

	write_config(fsmirrors + selector.urls, options.output, config_path, options.rsync)


if __name__ == '__main__':
	main(sys.argv)
