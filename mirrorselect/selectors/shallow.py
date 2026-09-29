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

import concurrent.futures
import requests
import socket

from datetime import datetime, timezone
from mirrorselect.mirrorset import Endpoint
from urllib.parse import urlparse
from .helpers import urljoin

MAX_MIRROR_AGE_DAYS = 14

# The timestamp.mirmon file contains a UNIX timestamp as text
TIMESTAMP_FILENAME = "distfiles/timestamp.mirmon"


class Shallow:
    """
    Approximates an HTTP GET request/response as a quasi
    'round trip time', analogous the previous behaviour by
    netselect. Additionally, discards mirrors with a
    timestamp older than MAX_MIRROR_AGE_DAYS
    """

    def __init__(self, hosts: list[Endpoint], options, output):
        self._options = options
        self.output = output
        self._connect_timeout = options.timeout
        self.urls = []

        self.fetch_select(hosts, options.servers, options.blocksize)

        if len(self.urls) == 0:
            self.output.print_err("Could not find any mirrors.")

    def _probe_mirror(self, host: Endpoint, today: datetime):
        timestamp_uri = urljoin(host.uri, TIMESTAMP_FILENAME)
        url_parts = urlparse(host.uri)

        try:
            # First, ensure any DNS records are cached, prior to timing the
            # HTTP GET exchange, to ensure any mirrors already cached locally
            # aren't unduly advantaged.

            for addr_family in (socket.AF_INET, socket.AF_INET6):
                socket.getaddrinfo(
                    url_parts.hostname,
                    None,
                    addr_family,
                    socket.SOCK_STREAM,
                    0,
                    socket.AI_ADDRCONFIG,
                )

            response = requests.get(timestamp_uri, timeout=self._connect_timeout)

            # Log a 404 differently; a mirror that is functional but lacks a
            # timestamp entry is interesting from a diagnostics perspective.
            if response.status_code == 404:
                self.output.write(
                    f"_probe_mirror(): no timestamp.mirmon at {timestamp_uri}\n", 2
                )
                return
            if response.status_code != 200:
                self.output.write(
                    f"_probe_mirror(): got HTTP {response.status_code}"
                    f" fetching {timestamp_uri}\n",
                    2,
                )
                return

            age = today - datetime.fromtimestamp(int(response.text), timezone.utc)
            if age.days > MAX_MIRROR_AGE_DAYS:
                self.output.write(
                    f"{host.uri} has not updated in {age.days} days, dicarding\n",
                    1,
                )
                return

            return (host, age, response.elapsed.total_seconds())
        except ValueError:
            self.output.write(
                f"_probe_mirror(): couldn't parse timestamp {host.uri}\n",
                2,
            )
        except requests.exceptions.Timeout:
            self.output.write(
                f"_probe_mirror(): timeout connecting to host {host.uri}\n",
                2,
            )
        except OSError:
            self.output.write(
                f"_probe_mirror(): unable to connect to host {host.uri}\n",
                2,
            )

    def fetch_select(self, hosts: list[Endpoint], number, blocksize):
        today = datetime.now(timezone.utc)
        results = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=blocksize) as executor:
            futures = [
                executor.submit(self._probe_mirror, host, today) for host in hosts
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    if future.result() is not None:
                        results.append(future.result())
                        host, age, elapsed = future.result()
                        self.output.write(
                            f"{host.uri:40} age: {age} RTT: {elapsed}\n", 3
                        )
                except Exception as e:
                    self.output.write(f"error {e}\n", 2)

            # sort the results by the fetch time
            fastest = sorted(results, key=lambda item: item[2])
            self.urls = [result[0].uri for result in fastest[:number]]
