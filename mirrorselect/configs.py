#-*- coding:utf-8 -*-


"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2019 Gentoo Authors

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
import re
import shlex
import shutil
import string
import sys


letters = string.ascii_letters


def get_make_conf_path(EPREFIX):
		# try the newer make.conf location
		config_path = EPREFIX + '/etc/portage/make.conf'
		if not os.access(config_path, os.F_OK):
			# check if the old location is what is used
			if os.access(EPREFIX + '/etc/make.conf', os.F_OK):
				config_path = EPREFIX + '/etc/make.conf'
		return config_path


def write_make_conf(output, config_path, var, mirror_string):
	"""Write the make.conf target changes

	@param output: file, or output to print messages to
	@param mirror_string: "var='hosts'" string to write
	@param config_path; string
	"""
	output.write('\n')
	output.print_info('Modifying %s with new mirrors...\n' % config_path)
	try:
		config = open(config_path, 'r')
		output.write('\tReading make.conf\n')
		lines = config.readlines()
		config.close()
		output.write('\tMoving to %s.backup\n' % config_path)
		shutil.move(config_path, config_path + '.backup')
	except IOError:
		lines = []

	with open(config_path + '.backup', 'r') as f:
		lex = shlex.shlex(f, posix=True)
		lex.wordchars = string.digits + letters + r"~!@#$%*_\:;?,./-+{}"
		lex.quotes = "\"'"
		while True:
			key = lex.get_token()
			if key is None:
				break

			if key == var:
				begin_line = lex.lineno
				equ = lex.get_token()
				if equ is None:
					break
				if equ != '=':
					continue

				val = lex.get_token()
				if val is None:
					break
				end_line = lex.lineno

				new_lines = []
				for index, line in enumerate(lines):
					if index < begin_line - 1 or index >= end_line - 1:
						new_lines.append(line)
				lines = new_lines
				break

	lines.append(mirror_string)

	output.write('\tWriting new %s\n' % config_path)

	config = open(config_path, 'w')

	for line in lines:
		config.write(line)
	config.write('\n')
	config.close()

	output.print_info('Done.\n')


def write_repos_conf(output, config_path, var, value):
	"""Saves the new var value to a ConfigParser style file

	@param output: file, or output to print messages to
	@param config_path; string
	@param var: string; the variable to save teh value to.
	@param value: string, the value to set var to
	"""
	try:
		from configparser import ConfigParser
	except ImportError:
		from ConfigParser import ConfigParser
	config = ConfigParser()
	config.read(config_path)
	if config.has_option('gentoo', var):
		config.set('gentoo', var, value)
		with open(config_path, 'w') as configfile:
			config.write(configfile)
	else:
		output.print_err("write_repos_conf(): Failed to find section 'gentoo',"
			" variable: %s\nChanges NOT SAVED" %var)


def get_filesystem_mirrors(output, config_path):
	"""Read the current mirrors and retain mounted filesystems mirrors

	@param config_path: string
	@rtype list
	"""

	def get_token(lex):
		'''internal function for getting shlex tokens
		'''
		try:
			val = lex.get_token()
		except ValueError:
			val = None
		return val

	fsmirrors = []

	var = 'GENTOO_MIRRORS'

	output.write('get_filesystem_mirrors(): config_path = %s\n' % config_path, 2)
	try:
		f = open(config_path,'r')
	except IOError:
		return fsmirrors

	""" Search for 'var' in make.conf and extract value """
	lex = shlex.shlex(f, posix=True)
	lex.wordchars = string.digits + letters + r"~!@#$%*_\:;?,./-+{}"
	lex.quotes = "\"'"
	p = re.compile('rsync://|http://|https://|ftp://', re.IGNORECASE)
	while 1:
		key = get_token(lex)
		#output.write('get_filesystem_mirrors(): processing key = %s\n' % key, 2)

		if key == var:
			equ = get_token(lex)
			if (equ != '='):
				break

			val = get_token(lex)
			if val is None:
				break

			""" Look for mounted filesystem in value """
			mirrorlist = val.rsplit()
			output.write('get_filesystem_mirrors(): mirrorlist = %s\n' % mirrorlist, 2)
			for mirror in mirrorlist:
				if (p.match(mirror) == None):
					if os.access(mirror, os.F_OK):
						output.write('get_filesystem_mirrors(): found file system mirror = %s\n' % mirror, 2)
						fsmirrors.append(mirror)
					else:
						output.write('get_filesystem_mirrors(): ignoring non-accessible mirror = %s\n' % mirror, 2)
			break
		elif key is None:
			break

	output.write('get_filesystem_mirrors(): fsmirrors = %s\n' % fsmirrors, 2)
	return fsmirrors


