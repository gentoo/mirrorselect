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
from abc import ABC
from typing import Any
from mirrorselect.mirrorparser3 import MIRRORS_3_XML, MIRRORS_RSYNC_DATA
from mirrorselect.extractor import Extractor

from mirrorselect.output import Output

letters = string.ascii_letters

class Configuration(ABC):
    def __init__(self, var: str, eprefix: str):
        self.eprefix = eprefix
        self.var = var

    def get_filesystem_mirrors(self, output: Output, config_path: str):
        """Read the current mirrors and retain mounted filesystems mirrors

        @param config_path: string
        @rtype list
        """

        def get_token(lex: shlex.shlex):
            """internal function for getting shlex tokens"""
            try:
                val = lex.get_token()
            except ValueError:
                val = None
            return val

        fsmirrors: list[str] = []

        output.write("get_filesystem_mirrors(): config_path = %s\n" % config_path, 2)
        try:
            f = open(config_path)
        except OSError:
            return fsmirrors

        """ Search for 'var' in config file and extract value """
        lex = shlex.shlex(f, posix=True)
        lex.wordchars = string.digits + letters + r"~!@#$%*_\:;?,./-+{}"
        lex.quotes = "\"'"
        p = re.compile("rsync://|http://|https://|ftp://", re.IGNORECASE)
        while True:
            key = get_token(lex)
            # output.write('get_filesystem_mirrors(): processing key = %s\n' % key, 2)

            if key == self.var:
                equ = get_token(lex)
                if equ != "=":
                    break

                val = get_token(lex)
                if val is None:
                    break

                """ Look for mounted filesystem in value """
                mirrorlist = val.rsplit()
                output.write("get_filesystem_mirrors(): mirrorlist = %s\n" % mirrorlist, 2)
                for mirror in mirrorlist:
                    if p.match(mirror) is None:
                        if os.access(mirror, os.F_OK):
                            output.write(
                                "get_filesystem_mirrors(): found file system mirror = %s\n"
                                % mirror,
                                2,
                            )
                            fsmirrors.append(mirror)
                        else:
                            output.write(
                                "get_filesystem_mirrors(): ignoring non-accessible mirror = %s\n"
                                % mirror,
                                2,
                            )
                break
            elif key is None:
                break

        output.write("get_filesystem_mirrors(): fsmirrors = %s\n" % fsmirrors, 2)
        return fsmirrors

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

    def get_available_hosts(self, output: Output, options):
        output.write("using url: %s\n" % MIRRORS_3_XML, 2)
        return Extractor(MIRRORS_3_XML, options, output).hosts

    def format_config(self, hosts: list[str]):
        return '{}="{}"'.format(self.var, " \\\n    ".join(hosts))


class RsyncConfig(Configuration):
    def __init__(self, eprefix: str = ""):
        super().__init__("sync-uri", eprefix)

    def get_conf_path(self, output: Output):
        config_path = self.eprefix + "/etc/portage/repos.conf/gentoo.conf"
        if not os.access(config_path, os.F_OK):
            output.write(
                "Failed access to gentoo.conf: "
                "%s\n" % os.access(config_path, os.F_OK),
                2,
            )
            config_path = None
        return config_path

    def get_available_hosts(self, output: Output, options: dict[str, Any]):
        output.write("using url: %s\n" % MIRRORS_RSYNC_DATA, 2)
        return Extractor(MIRRORS_RSYNC_DATA, options, output).hosts

    def format_config(self, hosts: list[str]):
        return "{} = {}".format(self.var, " ".join(hosts))

    def write_config(self, output: Output, config_path: str, hosts: list[str]):
        """Saves the new var value to a ConfigParser style file

        @param output: file, or output to print messages to
        @param config_path; string
        @param var: string; the variable to save the value to.
        @param value: string, the value to set var to
        """
        from configparser import ConfigParser
        config = ConfigParser()
        config.read(config_path)
        if config.has_option("gentoo", self.var):
            config.set("gentoo", self.var, " ".join(hosts))
            with open(config_path, "w") as configfile:
                config.write(configfile)
        else:
            output.print_err(
                "write_repos_conf(): Failed to find section 'gentoo',"
                " variable: %s\nChanges NOT SAVED" % self.var
            )


