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


import sys
import re

from optparse import IndentedHelpFormatter


class Output(object):
	"""Handles text output. Only prints messages with level <= verbosity.
	Therefore, verbosity=2 is everything (debug), and verbosity=0 is urgent
	messages only (quiet)."""

	def __init__(self, verbosity=1, out=sys.stderr):
		esc_seq = "\x1b["
		codes = {}

		codes["reset"]     = esc_seq + "39;49;00m"
		codes["bold"]      = esc_seq + "01m"
		codes["blue"]      = esc_seq + "34;01m"
		codes["green"]     = esc_seq + "32;01m"
		codes["yellow"]    = esc_seq + "33;01m"
		codes["red"]       = esc_seq + "31;01m"

		self.codes = codes
		del codes

		self.verbosity = verbosity
		self.file = out

	def red(self, text):
		return self.codes["red"]+text+self.codes["reset"]

	def green(self, text):
		return self.codes["green"]+text+self.codes["reset"]

	def white(self, text):
		return self.codes["bold"]+text+self.codes["reset"]

	def blue(self, text):
		return self.codes["blue"]+text+self.codes["reset"]

	def yellow(self, text):
		return self.codes["yellow"]+text+self.codes["reset"]

	def print_info(self, message, level=1):
		"""Prints an info message with a green star, like einfo."""
		if level <= self.verbosity:
			self.file.write('\r' + self.green('* ') + message)
			self.file.flush()

	def print_warn(self, message, level=1):
		"""Prints a warning."""
		if level <= self.verbosity:
			self.file.write(self.yellow('Warning: ') + message)
			self.file.flush()

	def print_err(self, message, level=0):
		"""prints an error message with a big red ERROR."""
		if level <= self.verbosity:
			self.file.write(self.red('\nERROR: ') + message + '\n')
			self.file.flush()
			sys.exit(1)

	def write(self, message, level=1):
		"""A wrapper arounf stderr.write, to enforce verbosity settings."""
		if level <= self.verbosity:
			self.file.write(message)
			self.file.flush()


class ColoredFormatter(IndentedHelpFormatter):

	"""HelpFormatter with colorful output.

	Extends format_option.
	Overrides format_heading.
	"""

	def __init__(self, output):
		self.output = output

	def format_heading(self, heading):
		"""Return a colorful heading."""
		return "%*s%s:\n" % (self.current_indent, "", self.output.white(heading))

	def format_option(self, option):
		"""Return colorful formatted help for an option."""
		option = IndentedHelpFormatter.format_option(self, option)
		# long options with args
		option = re.sub(
			r"--([a-zA-Z]*)=([a-zA-Z]*)",
			lambda m: "-%s %s" % (self.output.green(m.group(1)),
				self.output.blue(m.group(2))),
			option)
		# short options with args
		option = re.sub(
			r"-([a-zA-Z]) ?([0-9A-Z]+)",
			lambda m: " -" + self.output.green(m.group(1)) + ' ' + \
				self.output.blue(m.group(2)),
			option)
		# options without args
		option = re.sub(
			r"-([a-zA-Z\d]+)", lambda m: "-" + self.output.green(m.group(1)),
			option)
		return option

	def format_description(self, description):
		"""Do not wrap."""
		return description + '\n'

