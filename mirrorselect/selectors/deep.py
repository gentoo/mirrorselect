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

import http.client
import math
import signal
import socket
import ssl
import time
import hashlib
import itertools

from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from optparse import Values
from mirrorselect.output import Output
from mirrorselect.mirrorset import Endpoint
from portage.package.ebuild.fetch import (
        MirrorLayoutConfig,
        FlatLayout,
        )
from configparser import (
        ConfigParser,
        Error as ConfigParseError
        )

class TimeoutException(Exception):
    pass


def timeout_handler(*_):
    raise TimeoutException()

class Deep:
    """handles deep mode mirror selection."""

    def __init__(self, hosts: list[Endpoint], options: Values, output: Output):
        self.output = output
        self.urls: list[str] = []
        self._hosts = hosts
        self._number = options.servers
        self._dns_timeout = options.timeout
        self._connect_timeout = options.timeout
        self._download_timeout: float = options.timeout
        self.test_file = options.file
        self.test_md5 = options.md5

        addr_families: list[int] = []
        if options.ipv4:
            addr_families.append(socket.AF_INET)
        elif options.ipv6:
            addr_families.append(socket.AF_INET6)
        else:
            addr_families.append(socket.AF_UNSPEC)

        self._addr_families = addr_families

        self.deeptest()

    def deeptest(self):
        """
        Takes a list of hosts and returns the fastest, using _deeptime()
        Doesn't waste time finnishing a test that has already taken longer than
        the slowest mirror weve already got.
        """
        prog = 0
        maxtime = self._download_timeout
        num_hosts = len(self._hosts)
        self.dl_failures = 0
        results: list[tuple[float, Endpoint]] = []

        for host in self._hosts:
            prog += 1
            if self.test_file != "mirrorselect-test":
                self.output.print_info(
                    "Downloading %s files from each mirror... [%s of %s]"
                    % (self.test_file, prog, num_hosts)
                )
            else:
                self.output.print_info(
                    "Downloading 100k files from each mirror... [%s of %s]"
                    % (prog, num_hosts)
                )

            mytime, _ = self.deeptime(host.uri, maxtime)

            if mytime is None:
                continue

            results.append((mytime, host))
            if len(results) >= self._number:
                """we can now start bailing out of tests that are slower
                than the nth fastest host in the list"""

                maxtime = max(sorted(results)[:self._number])[0]

        fastest_hosts = [test[1].uri for test in sorted(results)[:self._number]]

        self.output.write(
            "deeptest(): got %s hosts, and returned %s\n"
            % (num_hosts, str(fastest_hosts)),
            2,
        )

        self.output.write("\n")  # this just makes output nicer

        self.output.write(
            f"deeptest(): final md5 failures {self.dl_failures} of {num_hosts}\n",
            2,
        )
        self.urls = fastest_hosts

    def get_distfile_structure(self, distfiles_url: str):
        """
        Obtain the GLEP 75 Mirror Layout from layout.conf

        This is a modification  of that found in portage
        in package/ebuild/fetch.py, however that implementation
        requires storing the layout.conf as a temporary file.

        GLEP 75 explains the mechanism for mirrors to communicate
        the path schema they use.
        See: https://www.gentoo.org/glep/glep-0075.html
        """
        config_parser = ConfigParser()
        config_url = Deep._urljoin(distfiles_url, "layout.conf")

        self.output.write(f"_get_distfile_structure(): config_url = {config_url}\n", 2)

        response = urlopen(config_url, None, self._connect_timeout)

        if response.status == 404:
            self.output.write("_get_distfile_structure(): no layout.conf, assuming flat\n", 2)
            # mirrors lacking a layout.conf are assume to use a flat layout
            return FlatLayout()

        config_parser.read_string(response.read().decode('utf-8'))
        vals = []

        for i in itertools.count():
            try:
                vals.append(tuple(config_parser.get("structure", "%d" % i).split()))
            except ConfigParseError:
                break

        mlc = MirrorLayoutConfig()
        mlc.deserialize(vals)
        return mlc.get_best_supported_layout()

    def deeptime(self, url: str, maxtime: float):
        """
        Takes a single url and fetch command, and downloads the test file.
        Can be given an optional timeout, for use with a clever algorithm.
        Like mine.
        """
        self.output.write("\n_deeptime(): maxtime is %s\n" % maxtime, 2)

        dist_url = Deep._urljoin(url, "distfiles")

        try: 
            structure = self.get_distfile_structure(dist_url)
        except OSError as e:
            self.output.write(
                f"deeptime(): unable to connect to host {url}\n",
                2,
            )
            return (None, True)

        path: str = structure.get_path(self.test_file)
        url = self._urljoin(dist_url, path)
        url_parts = urlparse(url)

        self.output.write(f"_deeptime(): testfile url = {url}\n", 1)

        signal.signal(signal.SIGALRM, timeout_handler)

        ips = []
        for addr_family in self._addr_families:
            try:
                try:
                    signal.alarm(self._dns_timeout)
                    for result in socket.getaddrinfo(
                        url_parts.hostname,
                        None,
                        addr_family,
                        socket.SOCK_STREAM,
                        0,
                        socket.AI_ADDRCONFIG,
                    ):
                        family, _, __, ___, sockaddr = result
                        ip = sockaddr[0]
                        if family == socket.AF_INET6:
                            ip = "[%s]" % ip
                        ips.append(ip)
                finally:
                    signal.alarm(0)
            except OSError as e:
                self.output.write(
                    f"deeptime(): dns error for host {url_parts.hostname}: {e}\n",
                    2,
                )
            except TimeoutException:
                self.output.write(
                    "deeptime(): dns timeout for host %s\n" % url_parts.hostname, 2
                )

        if not ips:
            self.output.write(
                "deeptime(): unable to resolve ip for host %s\n" % url_parts.hostname, 2
            )
            return (None, True)

        self.output.write(
            f"deeptime(): ip's for host {url_parts.hostname}: {str(ips)}\n", 2
        )
        delta = 0
        f = None

        for ip in ips:
            test_parts = url_parts._replace(netloc=ip)
            test_url = urlunparse(test_parts)
            self.output.write("deeptime(): testing url: %s\n" % test_url, 2)

            f, test_url, early_out = self._test_connection(
                test_url, url_parts, ip, ips[ips.index(ip) :]
            )
            if early_out:
                break

        if f is None:
            self.output.write(
                f"deeptime(): unable to connect to host {url_parts.hostname}\n",
                2,
            )
            return (None, True)

        try:
            # Close the initial "wake up" connection.
            try:
                signal.alarm(self._connect_timeout)
                f.close()
            finally:
                signal.alarm(0)
        except OSError as e:
            self.output.write(
                ("deeptime(): closing connection to host %s " "failed for ip %s: %s\n")
                % (url_parts.hostname, ip, e),
                2,
            )
        except TimeoutException:
            self.output.write(
                ("deeptime(): closing connection to host %s " "timed out for ip %s\n")
                % (url_parts.hostname, ip),
                2,
            )

        self.output.write("deeptime(): timing url: %s\n" % test_url, 2)
        try:
            # The first connection serves to "wake up" the route between
            # the local and remote machines. A second connection is used
            # for the timed run.
            try:
                signal.alarm(int(math.ceil(maxtime)))
                stime = time.time()
                r = Request(test_url)
                r.host = url_parts.netloc
                f = urlopen(r)

                md5 = hashlib.md5(f.read()).hexdigest()

                delta = time.time() - stime
                f.close()
                if md5 != self.test_md5:
                    self.output.write(
                        "\ndeeptime(): md5sum error for file: %s\n" % self.test_file
                        + "         expected: %s\n" % self.test_md5
                        + "         got.....: %s\n" % md5
                        + f"         host....: {url_parts.hostname}, {ip}\n"
                    )
                    self.dl_failures += 1
                    return (None, True)

            finally:
                signal.alarm(0)

        except (OSError, ssl.CertificateError) as e:
            self.output.write(
                ("\ndeeptime(): download from host %s " "failed for ip %s: %s\n")
                % (url_parts.hostname, ip, e),
                2,
            )
            return (None, True)
        except TimeoutException:
            self.output.write(
                ("\ndeeptime(): download from host %s " "timed out for ip %s\n")
                % (url_parts.hostname, ip),
                2,
            )
            return (None, True)
        except http.client.IncompleteRead as e:
            self.output.write(
                ("\ndeeptime(): download from host %s " "failed for ip %s: %s\n")
                % (url_parts.hostname, ip, e),
                2,
            )
            return (None, True)

        signal.signal(signal.SIGALRM, signal.SIG_DFL)

        self.output.write("deeptime(): download completed.\n", 2)
        self.output.write(f"deeptime(): {delta} seconds for host {url}\n", 2)
        return (delta, False)

    def _test_connection(self, test_url, url_parts, ip, ips):
        """Tests the url for a connection, will recurse using
        the original url instead of the ip if an HTTPError occurs
        Returns f, test_url, early_out
        """
        early_out = False
        f = None
        try:
            try:
                signal.alarm(self._connect_timeout)
                r = Request(test_url)
                r.host = url_parts.netloc
                f = urlopen(r)
                early_out = True
            finally:
                signal.alarm(0)
        except HTTPError as e:
            self.output.write(
                "deeptime(): connection to host %s\n"
                "            returned HTTPError: %s for ip %s\n"
                "            Switching back to original url\n"
                % (url_parts.hostname, e, ip),
                2,
            )
            if len(ips) == 1:
                test_url = url_unparse(url_parts)
                return self._test_connection(test_url, url_parts, ip, [])
        except (OSError, ssl.CertificateError) as e:
            self.output.write(
                "deeptime(): connection to host %s "
                "failed for ip %s:\n            %s\n" % (url_parts.hostname, ip, e),
                2,
            )
        except TimeoutException:
            self.output.write(
                ("deeptime(): connection to host %s " "timed out for ip %s\n")
                % (url_parts.hostname, ip),
                2,
            )
        except Exception as e:  # Add general exception to catch any other errors
            self.output.print_warn(
                (
                    "deeptime(): connection to host %s "
                    "errored for ip %s\n            %s\n"
                    "          Please file a bug for this error at bugs.gentoo.org"
                )
                % (url_parts.hostname, ip, e),
                0,
            )
        return f, test_url, early_out


    @staticmethod
    def _urljoin(url: str, path: str):
        """Appends a path component to a URL string.

        urllib's urljoin can't be relied on for this. If the given URL
        doesn't end with a slash, the last component is *replaced* instead
        of concatenated to.

        In addition, urllib.parse requires a workaround for other protocols
        such as rsync, otherwise the given path component simply replaces
        the URL.
        """
        if not url.endswith("/"):
            url = url + "/"

        return url + path

