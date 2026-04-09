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

from optparse import Values
import os
from mirrorselect.mirrorparser3 import MIRRORS_RSYNC_DATA
from mirrorselect.extractor import Extractor
from .configuration import Configuration
from mirrorselect.output import Output


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

    def get_available_hosts(self, output: Output, options: Values):
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


