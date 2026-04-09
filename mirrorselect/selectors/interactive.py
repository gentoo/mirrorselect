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

import subprocess
import sys

from mirrorselect.output import encoder, get_encoding, decode_selection
from mirrorselect.mirrorset import Endpoint


class Interactive:
    """Handles interactive host selection."""

    def __init__(self, hosts: list[Endpoint], options, output):
        self.output = output
        self.urls = []

        self.interactive(hosts, options)
        self.output.write("Interactive.interactive(): self.urls = %s\n" % self.urls, 2)

        if not self.urls or len(self.urls[0]) == 0:
            sys.exit(1)

    def interactive(self, hosts, options):
        """
        Some sort of interactive menu thingy.
        """
        if options.rsync:
            dialog = [
                "dialog",
                "--stdout",
                "--title",
                "Gentoo RSYNC Mirrors",
                "--radiolist",
                "Please select your desired mirror:",
            ]
        else:
            dialog = [
                "dialog",
                "--separate-output",
                "--stdout",
                "--title",
                "Gentoo Download Mirrors",
                "--checklist",
                "Please select your desired mirrors:",
            ]
            if not options.ipv4 and not options.ipv6:
                dialog[-1] += "\n* = supports ipv6"

        dialog.extend(["20", "110", "14"])

        for mirror in sorted(
            hosts, key=lambda x: (x.country.lower(), x.name.lower())
        ):
            marker = ""
            uri = mirror.uri
            if options.rsync and not uri.endswith("/gentoo-portage"):
                uri += "/gentoo-portage"
            if (not options.ipv6 and not options.ipv4) and mirror.ipv6 == "y":
                marker = "* "
            if options.ipv6 and (mirror.ipv6 == "n"):
                continue
            if options.ipv4 and (mirror.ipv4 == "n"):
                continue

            # dialog.append('"%s" "%s%s: %s" "OFF"'
            # % ( url, marker, args['country'], args['name']))
            dialog.extend(
                [
                    "%s" % uri,
                    f"{marker}{mirror.country}: {mirror.name}",
                    "OFF",
                ]
            )
        dialog = [encoder(x, get_encoding(sys.stdout)) for x in dialog]
        proc = subprocess.Popen(dialog, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        out, _ = proc.communicate()

        self.urls = out.splitlines()

        sys.stderr.write("\x1b[2J\x1b[H")
        if self.urls:
            if hasattr(self.urls[0], "decode"):
                self.urls = decode_selection(
                    [x.decode("utf-8").rstrip() for x in self.urls]
                )
            else:
                self.urls = decode_selection([x.rstrip() for x in self.urls])
