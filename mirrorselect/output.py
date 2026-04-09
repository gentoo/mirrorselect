#!/usr/bin/env python3

"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2026 Gentoo Authors

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
import codecs
import locale

from optparse import IndentedHelpFormatter, Option
from typing import Any, TextIO

def encoder(text: str, _encoding_: str):
    return codecs.encode(text, _encoding_, "replace")

def decode_selection(selection: list[str]):
    """utility function to decode a list of strings
    accoring to the filesystem encoding
    """
    # fix None passed in, return an empty list
    selection = selection or []
    enc = sys.getfilesystemencoding()
    return [encoder(i, enc) for i in selection]

def get_encoding(output: TextIO | Any):
    if hasattr(output, "encoding") and output.encoding is not None:
        return output.encoding
    else:
        encoding = locale.getpreferredencoding()
        # Make sure that python knows the encoding. Bug 350156
        try:
            # We don't care about what is returned, we just want to
            # verify that we can find a codec.
            codecs.lookup(encoding)
        except LookupError:
            # Python does not know the encoding, so use utf-8.
            encoding = "utf_8"
        return encoding


class Output:
    """Handles text output. Only prints messages with level <= verbosity.
    Therefore, verbosity=2 is everything (debug), and verbosity=0 is urgent
    messages only (quiet)."""

    def __init__(self, verbosity: int = 1, out: TextIO | Any = sys.stderr):
        esc_seq = "\x1b["
        codes = {}

        codes["reset"] = esc_seq + "39;49;00m"
        codes["bold"] = esc_seq + "01m"
        codes["blue"] = esc_seq + "34;01m"
        codes["green"] = esc_seq + "32;01m"
        codes["yellow"] = esc_seq + "33;01m"
        codes["red"] = esc_seq + "31;01m"

        self.codes: dict[str, str] = codes
        del codes

        self.verbosity = verbosity
        self.file = out

    def red(self, text: str):
        return self.codes["red"] + text + self.codes["reset"]

    def green(self, text: str):
        return self.codes["green"] + text + self.codes["reset"]

    def white(self, text: str):
        return self.codes["bold"] + text + self.codes["reset"]

    def blue(self, text: str):
        return self.codes["blue"] + text + self.codes["reset"]

    def yellow(self, text: str):
        return self.codes["yellow"] + text + self.codes["reset"]

    def print_info(self, message: str, level: int = 1):
        """Prints an info message with a green star, like einfo."""
        if level <= self.verbosity:
            self.file.write("\r" + self.green("* ") + message)
            self.file.flush()

    def print_warn(self, message: str, level: int = 1):
        """Prints a warning."""
        if level <= self.verbosity:
            self.file.write(self.yellow("Warning: ") + message)
            self.file.flush()

    def print_err(self, message: str, level: int = 0):
        """Prints an error message with a big red ERROR."""
        if level <= self.verbosity:
            self.file.write(self.red("\nERROR: ") + message + "\n")
            self.file.flush()
            sys.exit(1)

    def write(self, message: str, level: int = 1):
        """A wrapper around stderr.write, to enforce verbosity settings."""
        if level <= self.verbosity:
            self.file.write(message)
            self.file.flush()


class ColoredFormatter(IndentedHelpFormatter):

    """HelpFormatter with colorful output.

    Extends format_option.
    Overrides format_heading.
    """

    def __init__(self, output: Output):
        IndentedHelpFormatter.__init__(self)
        self.output = output

    def format_heading(self, heading: str):
        """Return a colorful heading."""
        return "%*s%s:\n" % (self.current_indent, "", self.output.white(heading))

    def format_option(self, option: Option):
        """Return colorful formatted help for an option."""
        colored = IndentedHelpFormatter.format_option(self, option)
        # long options with args
        colored = re.sub(
            r"--([a-zA-Z]*)=([a-zA-Z]*)",
            lambda m: "-{} {}".format(
                self.output.green(m.group(1)), self.output.blue(m.group(2))
            ),
            colored,
        )
        # short options with args
        colored = re.sub(
            r"-([a-zA-Z]) ?([0-9A-Z]+)",
            lambda m: " -"
            + self.output.green(m.group(1))
            + " "
            + self.output.blue(m.group(2)),
            colored,
        )
        # options without args
        colored = re.sub(
            r"-([a-zA-Z\d]+)", lambda m: "-" + self.output.green(m.group(1)), colored
        )
        return colored

    def format_description(self, description: str | None):
        """Do not wrap."""
        if not description:
            return "\n"
        return description + "\n"
