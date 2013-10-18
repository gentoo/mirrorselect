#!/usr/bin/env python
#-*- coding:utf-8 -*-

"""Mirrorselect 2.x
 Tool for selecting Gentoo source and rsync mirrors.

Copyright 2005-2012 Gentoo Foundation

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

import math
import signal
import socket
import subprocess
import sys
import time
import hashlib

if sys.version_info[0] >= 3:
	import urllib.request, urllib.parse, urllib.error
	url_parse = urllib.parse.urlparse
	url_open = urllib.request.urlopen
else:
	import urllib
	import urlparse
	url_parse = urlparse.urlparse
	url_open = urllib.urlopen


from mirrorselect.output import encoder, get_encoding, decode_selection


class Shallow(object):
	"""handles rapid server selection via netselect"""

	def __init__(self, hosts, options, output):
		self.output = output
		self.urls = []

		if options.blocksize is not None:
			self.netselect_split(hosts, options.servers,
					options.blocksize)
		else:
			self.netselect(hosts, options.servers)

		if len(self.urls) == 0:
			self.output.print_err('Netselect failed to return any mirrors.'
					' Try again using block mode.')


	def netselect(self, hosts, number, quiet=False):
		"""
		Uses Netselect to choose the closest hosts, _very_ quickly
		"""
		if not quiet:
			hosts = [host[0] for host in hosts]
		top_host_dict = {}
		top_hosts = []

		if not quiet:
			self.output.print_info('Using netselect to choose the top %d mirrors...' \
					% number)

		host_string = ' '.join(hosts)

		self.output.write('\nnetselect(): running "netselect -s%d %s"\n' % (int(number),
			host_string), 2)

		proc = subprocess.Popen( ['netselect', '-s%d' % (number,)] + hosts,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		out, err = proc.communicate()

		if err:
			self.output.write('netselect(): netselect stderr: %s\n' % err, 2)

		for line in out.splitlines():
			line = line.split()
			if len(line) < 2:
				continue
			top_hosts.append(line[1])
			top_host_dict[line[0]] = line[1]

		if not quiet:
			self.output.write('Done.\n')

		self.output.write('\nnetselect(): returning %s and %s\n' % (top_hosts,
			top_host_dict), 2)

		if quiet:
			return top_hosts, top_host_dict
		else:
			self.urls = top_hosts


	def netselect_split(self, hosts, number, block_size):
		"""
		This uses netselect to test mirrors in chunks, each at most block_size in length.
		This is done in a tournament style.
		"""
		hosts = [host[0] for host in hosts]

		self.output.write('netselect_split() got %s hosts.\n' % len(hosts), 2)

		host_blocks = self.host_blocks(hosts, block_size)

		self.output.write(' split into %s blocks\n' % len(host_blocks), 2)

		top_hosts = []
		ret_hosts = {}

		block_index = 0
		for block in host_blocks:
			self.output.print_info('Using netselect to choose the top '
			'%d hosts, in blocks of %s. %s of %s blocks complete.'
			% (number, block_size, block_index, len(host_blocks)))

			host_dict = self.netselect(block, len(block), quiet=True)[1]

			self.output.write('ran netselect(%s, %s), and got %s\n' % (block, len(block),
				host_dict), 2)

			for key in list(host_dict.keys()):
				ret_hosts[key] = host_dict[key]
			block_index += 1

		sys.stderr.write('\rUsing netselect to choose the top'
		'%d hosts, in blocks of %s. %s of %s blocks complete.\n'
		% (number, block_size, block_index, len(host_blocks)))

		host_ranking_keys = list(ret_hosts.keys())
		host_ranking_keys.sort()

		for rank in host_ranking_keys[:number]:
			top_hosts.append(ret_hosts[rank])

		self.output.write('netselect_split(): returns %s\n' % top_hosts, 2)

		self.urls = top_hosts


	def host_blocks(self, hosts, block_size):
		"""
		Takes a list of hosts and a block size, and returns an list of lists of URLs.
		Each of the sublists is at most block_size in length.
		"""
		host_array = []
		mylist = []

		while len(hosts) > block_size:
			while (len(mylist) < block_size):
				mylist.append(hosts.pop())
			host_array.append(mylist)
			mylist = []
		host_array.append(hosts)

		self.output.write('\n_host_blocks(): returns %s blocks, each about %s in size\n'
				% (len(host_array), len(host_array[0])), 2)

		return host_array


class Deep(object):
	"""handles deep mode mirror selection."""

	def __init__(self, hosts, options, output):
		self.output = output
		self.urls = []
		self._hosts = hosts
		self._number = options.servers
		self._dns_timeout = options.timeout
		self._connect_timeout = options.timeout
		self._download_timeout = options.timeout
		self.test_file = options.file
		self.test_md5 = options.md5

		addr_families = []
		if options.ipv4:
			addr_families.append(socket.AF_INET)
		elif options.ipv6:
			addr_families.append(socket.AF_INET6)
		else:
			addr_families.append(socket.AF_INET)
			if socket.has_ipv6:
				addr_families.append(socket.AF_INET6)

		self._addr_families = addr_families

		self.deeptest()

	def deeptest(self):
		"""
		Takes a list of hosts and returns the fastest, using _deeptime()
		Doesn't waste time finnishing a test that has already taken longer than
		the slowest mirror weve already got.
		"""
		top_hosts = {}
		prog = 0
		maxtime = self._download_timeout
		hosts = [host[0] for host in self._hosts]
		num_hosts = len(hosts)

		for host in hosts:

			prog += 1
			if self.test_file is not 'mirrorselect-test':
				self.output.print_info('Downloading %s files from each mirror... [%s of %s]'\
								% (self.test_file, prog, num_hosts) )
			else:
				self.output.print_info('Downloading 100k files from each mirror... [%s of %s]'\
								% (prog, num_hosts) )

			mytime, ignore = self.deeptime(host, maxtime)

			if not ignore and mytime < maxtime:
				maxtime, top_hosts = self._list_add((mytime, host), \
						maxtime, top_hosts, self._number)
			else:
				continue

		self.output.write('deeptest(): got %s hosts, and returned %s\n' % (num_hosts, \
			str(list(top_hosts.values()))), 2)

		self.output.write('\n')	#this just makes output nicer

		#can't just return the dict.values, because we want the fastest mirror first...
		keys = list(top_hosts.keys())
		keys.sort()

		rethosts = []
		for key in keys:
			#self.output.write('deeptest(): adding rethost %s, %s' % (key, top_hosts[key]), 2)
			rethosts.append(top_hosts[key])

		self.output.write('deeptest(): final rethost %s' % (rethosts), 2)
		self.urls = rethosts


	def deeptime(self, url, maxtime):
		"""
		Takes a single url and fetch command, and downloads the test file.
		Can be given an optional timeout, for use with a clever algorithm.
		Like mine.
		"""
		self.output.write('\n_deeptime(): maxtime is %s\n' % maxtime, 2)

		if url.endswith('/'):	#append the path to the testfile to the URL
			url = url + 'distfiles/' + self.test_file
		else:
			url = url + '/distfiles/' + self.test_file

		url_parts = url_parse(url)

		class TimeoutException(Exception):
			pass

		def timeout_handler(signum, frame):
			raise TimeoutException()

		signal.signal(signal.SIGALRM, timeout_handler)

		ips = []
		for family in self._addr_families:
			ipv6 = family == socket.AF_INET6
			try:
				try:
					signal.alarm(self._dns_timeout)
					for family, socktype, proto, canonname, sockaddr in \
						socket.getaddrinfo(url_parts.hostname, None,
							family, socket.SOCK_STREAM):
						ip = sockaddr[0]
						if ipv6:
							ip = "[%s]" % ip
						ips.append(ip)
				finally:
					signal.alarm(0)
			except socket.error as e:
				self.output.write('deeptime(): dns error for host %s: %s\n' % \
					(url_parts.hostname, e), 2)
			except TimeoutException:
				self.output.write('deeptime(): dns timeout for host %s\n' % \
					(url_parts.hostname,), 2)

		if not ips:
			self.output.write('deeptime(): unable to resolve ip for host %s\n' % \
				(url_parts.hostname,), 2)
			return (None, True)

		delta = 0
		f = None

		for ip in ips:
			try:
				try:
					signal.alarm(self._connect_timeout)
					f = url_open(url)
					break
				finally:
					signal.alarm(0)
			except EnvironmentError as e:
				self.output.write(('deeptime(): connection to host %s ' + \
					'failed for ip %s: %s\n') % \
					(url_parts.hostname, ip, e), 2)
			except TimeoutException:
				self.output.write(('deeptime(): connection to host %s ' + \
					'timed out for ip %s\n') % \
					(url_parts.hostname, ip), 2)

		if f is None:
			self.output.write('deeptime(): unable to ' + \
				'connect to host %s\n' % \
				(url_parts.hostname,), 2)
			return (None, True)

		try:
			# Close the initial "wake up" connection.
			try:
				signal.alarm(self._connect_timeout)
				f.close()
			finally:
				signal.alarm(0)
		except EnvironmentError as e:
			self.output.write(('deeptime(): close connection to host %s ' + \
				'failed for ip %s: %s\n') % \
				(url_parts.hostname, ip, e), 2)
		except TimeoutException:
			self.output.write(('deeptime(): close connection to host %s ' + \
				'timed out for ip %s\n') % \
				(url_parts.hostname, ip), 2)

		try:
			# The first connection serves to "wake up" the route between
			# the local and remote machines. A second connection is used
			# for the timed run.
			try:
				signal.alarm(int(math.ceil(maxtime)))
				stime = time.time()
				f = url_open(url)

				if hashlib.md5(f.read()).hexdigest() != "bdf077b2e683c506bf9e8f2494eeb044":
					return (None, True)

				delta = time.time() - stime
				f.close()
			finally:
				signal.alarm(0)

		except EnvironmentError as e:
			self.output.write(('deeptime(): download from host %s ' + \
				'failed for ip %s: %s\n') % \
				(url_parts.hostname, ip, e), 2)
			return (None, True)
		except TimeoutException:
			self.output.write(('deeptime(): download from host %s ' + \
				'timed out for ip %s\n') % \
				(url_parts.hostname, ip), 2)
			return (None, True)

		signal.signal(signal.SIGALRM, signal.SIG_DFL)

		self.output.write('deeptime(): download completed.\n', 2)
		self.output.write('deeptime(): %s seconds for host %s\n' % (delta, url), 2)
		return (delta, False)

	def _list_add(self, time_host, maxtime, host_dict, maxlen):
		"""
		Takes argumets ((time, host), maxtime, host_dict, maxlen)
		Adds a new time:host pair to the dictionary of top hosts.
		If the dictionary is full, the slowest host is removed to make space.
		Returns the new maxtime, be it the specified timeout, or the slowest host.
		"""
		if len(host_dict) < maxlen:	#still have room, and host is fast. add it.

			self.output.write('_list_add(): added host %s. with a time of %s\n' %
					(time_host[1], time_host[0]), 2)

			host_dict.update(dict([time_host]))
			times = list(host_dict.keys())
			times.sort()

		else: #We need to make room in the dict before we add. Kill the slowest.
			self.output.write('_list_add(): Adding host %s with a time of %s\n' %
					(time_host[1], time_host[0]), 2)
			times = list(host_dict.keys())
			times.sort()
			self.output.write('_list_add(): removing %s\n' % host_dict[times[-1]],
					2)
			del host_dict[times[-1]]
			host_dict.update(dict([time_host]))
			#done adding. now return the appropriate time
			times = list(host_dict.keys())
			times.sort()

		if len(host_dict) < maxlen:	#check again to choose new timeout
			self.output.write('_list_add(): host_dict is not full yet.'
					' reusing timeout of %s sec.\n' % maxtime, 2)
			retval = maxtime
		else:
			self.output.write('_list_add(): host_dict is full. Selecting the best'
			' timeout\n', 2)
			if times[-1] < maxtime:
				retval = times[-1]
			else:
				retval = maxtime

		self.output.write('_list_add(): new max time is %s seconds,'
				' and now len(host_dict)= %s\n' % (retval, len(host_dict)), 2)

		return retval, host_dict


class Interactive(object):
	"""Handles interactive host selection."""

	def __init__(self, hosts, options, output):
		self.output = output
		self.urls = []

		self.interactive(hosts, options)
		self.output.write('Interactive.interactive(): self.urls = %s\n' % self.urls, 2)

		if not self.urls or len(self.urls[0]) == 0:
			sys.exit(1)


	def interactive(self, hosts, options):
		"""
		Some sort of interactive menu thingy.
		"""
		if options.rsync:
			dialog = ['dialog', '--stdout', '--title', '"Gentoo RSYNC Mirrors"',
				'--radiolist', '"Please select your desired mirror:"',
				'20', '110', '14']
		else:
			dialog = ['dialog', '--separate-output', '--stdout', '--title',
				'"Gentoo Download Mirrors"', '--checklist',
				'"Please select your desired mirrors:']
			if not options.ipv4 and not options.ipv6:
				dialog[-1] += '\n* = supports ipv6'

			dialog.extend(['20', '110', '14'])

		for (url, args) in sorted(hosts, key = lambda x: (x[1]['country'].lower(), x[1]['name'].lower()) ):
			marker = ""
			if options.rsync and not url.endswith("/gentoo-portage"):
				url+="/gentoo-portage"
			if (not options.ipv6 and not options.ipv4) and args['ipv6'] == 'y':
				marker = "* "
			if options.ipv6 and ( args['ipv6'] == 'n' ): continue
			if options.ipv4 and ( args['ipv4'] == 'n' ): continue

			#dialog.append('"%s" "%s%s: %s" "OFF"' % ( url, marker, args['country'], args['name']))
			dialog.extend(["%s" %url,
				"%s%s: %s" %(marker, args['country'], args['name']),
				 "OFF"])
		dialog = [encoder(x, get_encoding(sys.stdout)) for x in dialog]
		proc = subprocess.Popen( dialog,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		out, err = proc.communicate()

		self.urls = out.splitlines()

		if self.urls:
			if hasattr(self.urls[0], 'decode'):
				self.urls = decode_selection([x.decode('utf-8').rstrip() for x in self.urls])
			else:
				self.urls = decode_selection([x.rstrip() for x in self.urls])

