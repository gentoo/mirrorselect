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
import re
import string
import shlex
from abc import ABC, abstractmethod
from mirrorselect.output import Output

class Configuration(ABC):
    def __init__(self, var: str, eprefix: str):
        self.eprefix = eprefix
        self.var = var

    @abstractmethod
    def get_conf_path(self, output: Output) -> str | None:
        pass

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
        lex.wordchars = string.digits + string.ascii_letters + r"~!@#$%*_\:;?,./-+{}"
        lex.quotes = "\"'"
        p = re.compile("rsync://|http://|https://|ftp://", re.IGNORECASE)
        while True:
            key = get_token(lex)

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
