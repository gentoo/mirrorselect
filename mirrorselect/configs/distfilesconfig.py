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

import os
import os.path
import shlex
import shutil
import string
from optparse import Values

from mirrorselect.extractor import Extractor
from mirrorselect.mirrorparser3 import MIRRORS_3_XML
from mirrorselect.output import Output

letters = string.ascii_letters
from .configuration import Configuration


class DistfilesConfig(Configuration):
    def __init__(self, confdir: str):
        super().__init__("GENTOO_MIRRORS", confdir)

    def get_conf_path(self, output: Output):
        # try the newer make.conf location
        config_path = os.path.join(self.confdir, "portage", "make.conf")
        if not os.path.exists(config_path):
            # check if the old location is what is used
            old_path = os.path.join(self.confdir, "make.conf")
            if os.path.exists(old_path):
                config_path = old_path
        return config_path

    def filter_config(self, config):
        lines = config.readlines()
        config.seek(0)
        lex = shlex.shlex(config, posix=True)
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
        return lines

    def write_config(self, output: Output, config_path: str, hosts: list[str]):
        """Write the make.conf target changes

        @param output: file, or output to print messages to
        @param mirror_string: "var='hosts'" string to write
        @param config_path; string
        """

        output.write("\n")
        output.print_info(f"Modifying {config_path} with new mirrors...\n")

        try:
            config = open(config_path, "r", encoding="utf-8")
        except FileNotFoundError:
            lines = []
        else:
            with config:
                lines = self.filter_config(config)

        lines.append(self.format_config(hosts) + "\n")

        output.write(f"\tWriting new {config_path}\n")

        try:
            os.rename(config_path, config_path + ".backup")
        except FileNotFoundError:
            pass

        with open(config_path, "w", encoding="utf-8") as config:
            config.writelines(lines)

        output.print_info("Done.\n")

    def get_available_hosts(self, output: Output, options: Values):
        output.write(f"using url: {MIRRORS_3_XML}\n", 2)
        return Extractor(MIRRORS_3_XML, options, output).hosts

    def format_config(self, hosts: list[str]):
        return '{}="{}"'.format(self.var, " \\\n    ".join(hosts))
