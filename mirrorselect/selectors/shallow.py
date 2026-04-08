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
import subprocess

from mirrorselect.mirrorset import Endpoint

# The netselect --ipv4 and --ipv6 options are supported only
# with >=net-analyzer/netselect-0.4[ipv6(+)].
NETSELECT_SUPPORTS_IPV4_IPV6 = True


class Shallow:
    """handles rapid server selection via netselect"""

    def __init__(self, hosts: list[Endpoint], options, output):
        self._options = options
        self.output = output
        self.urls = []

        if options.blocksize is not None:
            self.netselect_split(hosts, options.servers, options.blocksize)
        else:
            self.netselect(hosts, options.servers)

        if len(self.urls) == 0:
            self.output.print_err(
                "Netselect failed to return any mirrors." " Try again using block mode."
            )

    def netselect(self, hosts: list[Endpoint], number, quiet=False):
        """
        Uses Netselect to choose the closest hosts, _very_ quickly
        """
        if not quiet:
            hosts = [host.uri for host in hosts]
        top_host_dict = {}
        top_hosts = []

        if not quiet:
            self.output.print_info(
                "Using netselect to choose the top " "%d mirrors..." % number
            )

        host_string = " ".join(hosts)

        cmd = ["netselect", "-s%d" % (number,)]

        if NETSELECT_SUPPORTS_IPV4_IPV6:
            if self._options.ipv4:
                cmd.append("-4")
            elif self._options.ipv6:
                cmd.append("-6")

        cmd.extend(hosts)

        self.output.write('\nnetselect(): running "%s"\n' % " ".join(cmd), 2)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        out, err = proc.communicate()

        if err:
            self.output.write("netselect(): netselect stderr: %s\n" % err, 2)

        for line in out.splitlines():
            line = line.split()
            if len(line) < 2:
                continue
            top_hosts.append(line[1])
            top_host_dict[line[0]] = line[1]

        if not quiet:
            self.output.write("Done.\n")

        self.output.write(
            f"\nnetselect(): returning {top_hosts} and {top_host_dict}\n", 2
        )

        if quiet:
            return top_hosts, top_host_dict
        else:
            self.urls = top_hosts

    def netselect_split(self, hosts, number, block_size):
        """
        This uses netselect to test mirrors in chunks,
        each at most block_size in length.
        This is done in a tournament style.
        """
        hosts = [host[0] for host in hosts]

        self.output.write("netselect_split() got %s hosts.\n" % len(hosts), 2)

        host_blocks = self.host_blocks(hosts, block_size)

        self.output.write(" split into %s blocks\n" % len(host_blocks), 2)

        top_hosts = []
        ret_hosts = {}

        block_index = 0
        for block in host_blocks:
            self.output.print_info(
                "Using netselect to choose the top "
                "%d hosts, in blocks of %s. %s of %s blocks complete."
                % (number, block_size, block_index, len(host_blocks))
            )

            host_dict = self.netselect(block, len(block), quiet=True)[1]

            self.output.write(
                f"ran netselect({block}, {len(block)}), and got {host_dict}\n",
                2,
            )

            for key in list(host_dict.keys()):
                ret_hosts[key] = host_dict[key]
            block_index += 1

        sys.stderr.write(
            "\rUsing netselect to choose the top"
            "%d hosts, in blocks of %s. %s of %s blocks complete.\n"
            % (number, block_size, block_index, len(host_blocks))
        )

        host_ranking_keys = sorted(ret_hosts.keys())

        for rank in host_ranking_keys[:number]:
            top_hosts.append(ret_hosts[rank])

        self.output.write("netselect_split(): returns %s\n" % top_hosts, 2)

        self.urls = top_hosts

    def host_blocks(self, hosts, block_size):
        """
        Takes a list of hosts and a block size,
        and returns an list of lists of URLs.
        Each of the sublists is at most block_size in length.
        """
        host_array = []
        mylist = []

        while len(hosts) > block_size:
            while len(mylist) < block_size:
                mylist.append(hosts.pop())
            host_array.append(mylist)
            mylist = []
        host_array.append(hosts)

        self.output.write(
            "\n_host_blocks(): returns "
            "%s blocks, each about %s in size\n"
            % (len(host_array), len(host_array[0])),
            2,
        )

        return host_array


