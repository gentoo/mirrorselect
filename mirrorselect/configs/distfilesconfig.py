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

from optparse import Values
import os
import shlex
import shutil
import string
from mirrorselect.mirrorparser3 import MIRRORS_3_XML
from mirrorselect.extractor import Extractor

from mirrorselect.output import Output

letters = string.ascii_letters
from .configuration import Configuration


class DistfilesConfig(Configuration):
    def __init__(self, eprefix: str = ""):
        super().__init__("GENTOO_MIRRORS", eprefix)

    def get_conf_path(self, output: Output):
        # try the newer make.conf location
        config_path = self.eprefix + "/etc/portage/make.conf"
        if not os.access(config_path, os.F_OK):
            # check if the old location is what is used
            if os.access(self.eprefix + "/etc/make.conf", os.F_OK):
                config_path = self.eprefix + "/etc/make.conf"
        return config_path

    def write_config(self, output: Output, config_path: str, hosts: list[str]):
        """Write the make.conf target changes

        @param output: file, or output to print messages to
        @param mirror_string: "var='hosts'" string to write
        @param config_path; string
        """
        output.write("\n")
        output.print_info("Modifying %s with new mirrors...\n" % config_path)
        try:
            config = open(config_path)
            output.write("\tReading make.conf\n")
            lines = config.readlines()
            config.close()
            output.write("\tMoving to %s.backup\n" % config_path)
            shutil.move(config_path, config_path + ".backup")
        except OSError:
            lines = []

        with open(config_path + ".backup") as f:
            lex = shlex.shlex(f, posix=True)
            lex.wordchars = string.digits + letters + r"~!@#$%*_\:;?,./-+{}"
            lex.quotes = "\"'"
            while True:
                key = lex.get_token()
                if key is None:
                    break

                if key == self.var:
                    begin_line = lex.lineno
                    equ = lex.get_token()
                    if equ is None:
                        break
                    if equ != "=":
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

        lines.append(self.format_config(hosts))

        output.write("\tWriting new %s\n" % config_path)

        config = open(config_path, "w")

        for line in lines:
            config.write(line)
        config.write("\n")
        config.close()

        output.print_info("Done.\n")

    def get_available_hosts(self, output: Output, options: Values):
        output.write("using url: %s\n" % MIRRORS_3_XML, 2)
        return Extractor(MIRRORS_3_XML, options, output).hosts

    def format_config(self, hosts: list[str]):
        return '{}="{}"'.format(self.var, " \\\n    ".join(hosts))

