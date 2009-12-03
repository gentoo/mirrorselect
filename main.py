#!/usr/bin/python

# Mirrorselect 1.x
# Tool for selecting Gentoo source and rsync mirrors.
#
# Copyright (C) 2005 Colin Kingsley <tercel@gentoo.org>
# Copyright (C) 2008 Zac Medico <zmedico@gentoo.org>
# Copyright (C) 2009 Sebastian Pipping <sebastian@pipping.org>
# Copyright (C) 2009 Christian Ruppert <idl0r@gentoo.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.

__revision__ = '2.0.0'

import math
import os
import re
import shlex
import shutil
import signal
import socket
import string
import subprocess
import sys
import time
import urllib
import urlparse
from optparse import IndentedHelpFormatter, OptionParser
from mirrorselect.mirrorparser3 import MirrorParser3, MIRRORS_3_XML, MIRRORS_RSYNC_DATA
import codecs

class Output(object):
	"""Handles text output. Only prints messages with level <= verbosity.
	Therefore, verbosity=2 is everything (debug), and verbosity=0 is urgent
	messages only (quiet)."""

	def __init__(self, verbosity=1, out=sys.stderr):
		esc_seq = "\x1b["
		codes = {}
		
		codes["reset"]     = esc_seq + "39;49;00m"
		codes["bold"]      = esc_seq + "01m"
		codes["blue"]      = esc_seq + "34;01m"
		codes["green"]     = esc_seq + "32;01m"
		codes["yellow"]    = esc_seq + "33;01m"
		codes["red"]       = esc_seq + "31;01m"
		
		self.codes = codes
		del codes
		
		self.verbosity = verbosity
		self.file = out
	
	def red(self, text):
		return self.codes["red"]+text+self.codes["reset"]

	def green(self, text):
		return self.codes["green"]+text+self.codes["reset"]

	def white(self, text):
		return self.codes["bold"]+text+self.codes["reset"]

	def blue(self, text):
		return self.codes["blue"]+text+self.codes["reset"]

	def yellow(self, text):
		return self.codes["yellow"]+text+self.codes["reset"]
	
	def print_info(self, message, level=1):
		"""Prints an info message with a green star, like einfo."""
		if level <= self.verbosity:
			self.file.write('\r' + self.green('* ') + message)
			self.file.flush()
	
	def print_warn(self, message, level=1):
		"""Prints a warning."""
		if level <= self.verbosity:
			self.file.write(self.yellow('Warning: ') + message)
			self.file.flush()
	
	def print_err(self, message, level=0):
		"""prints an error message with a big red ERROR."""
		if level <= self.verbosity:
			self.file.write(self.red('\nERROR: ') + message + '\n')
			self.file.flush()
			sys.exit(1)
	
	def write(self, message, level=1):
		"""A wrapper arounf stderr.write, to enforce verbosity settings."""
		if level <= self.verbosity:
			self.file.write(message)
			self.file.flush()


class ColoredFormatter(IndentedHelpFormatter):

	"""HelpFormatter with colorful output.

	Extends format_option.
	Overrides format_heading.
	"""

	def format_heading(self, heading):
		"""Return a colorful heading."""
		return "%*s%s:\n" % (self.current_indent, "", output.white(heading))

	def format_option(self, option):
		"""Return colorful formatted help for an option."""
		option = IndentedHelpFormatter.format_option(self, option)
		# long options with args
		option = re.sub(
			r"--([a-zA-Z]*)=([a-zA-Z]*)",
			lambda m: "-%s %s" % (output.green(m.group(1)),
				output.blue(m.group(2))),
			option)
		# short options with args
		option = re.sub(
			r"-([a-zA-Z]) ?([0-9A-Z]+)",
			lambda m: " -" + output.green(m.group(1)) + ' ' + output.blue(m.group(2)),
			option)
		# options without args
		option = re.sub(
			r"-([a-zA-Z\d]+)", lambda m: "-" + output.green(m.group(1)),
			option)
		return option

	def format_description(self, description):
		"""Do not wrap."""
		return description + '\n'


class Extractor(object):
	"""The Extractor employs a MirrorParser3 object to get a list of valid
	mirrors, and then filters them. Only the mirrors that should be tested, based on
	user input are saved. They will be in the hosts attribute."""

	def __init__(self, list_url, options):
		parser = MirrorParser3()
		self.hosts = []
		
		hosts = self.getlist(parser, list_url)
		output.write('Extractor(): fetched mirrors.xml,'
				' %s hosts before filtering\n' % len(hosts), 2)

		if not options.rsync:
			if options.ftp:
				hosts = self.restrict_protocall('ftp', hosts)
			if options.http:
				hosts = self.restrict_protocall('http', hosts)

		self.hosts = hosts

	def restrict_protocall(self, prot, hosts):
		"""
		Removes hosts that are not of the specified type.
		"prot" must always be exactly 'http' or 'ftp'.
		"""
		myhosts = []

		output.print_info('Limiting test to %s hosts. ' % prot )
		
		for host in hosts:
			if host[0].startswith(prot):
				myhosts.append(host)
		
		output.write('%s of %s removed.\n' % (len(hosts) - len(myhosts),
			len(hosts)) )
		
		return myhosts
	
	
	def getlist(self, parser, url):
		"""
		Uses the supplied parser to get a list of urls.
		Takes a parser object, url, and filering options.
		"""

		output.write('getlist(): fetching ' + url + '\n', 2)
		
		output.print_info('Downloading a list of mirrors...')

		try:
			parser.parse(urllib.urlopen(url).read())
		except EnvironmentError:
			pass

		if len(parser.tuples()) == 0:
			output.print_err('Could not get mirror list. Check your internet'
					' connection.')

		output.write(' Got %d mirrors.\n' % len(parser.tuples()))

		return parser.tuples()


class Shallow(object):
	"""handles rapid server selection via netselect"""

	def __init__(self, hosts, options):
		self.urls = []
		
		if options.blocksize is not None:
			self.netselect_split(hosts, options.servers,
					options.blocksize)
		else:
			self.netselect(hosts, options.servers)

		if len(self.urls) == 0:
			output.print_err('Netselect failed to return any mirrors.'
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
			output.print_info('Using netselect to choose the top %d mirrors...' \
					% number)

		host_string = ' '.join(hosts)

		output.write('\nnetselect(): running "netselect -s%d %s"\n' % (int(number),
			host_string), 2)

		proc = subprocess.Popen( ['netselect', '-s%d' % (number,)] + hosts,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE)

		out, err = proc.communicate()

		if err:
			output.write('netselect(): netselect stderr: %s\n' % err, 2)

		for line in out.splitlines():
			line = line.split()
			if len(line) < 2:
				continue
			top_hosts.append(line[1])
			top_host_dict[line[0]] = line[1]
		
		if not quiet:
			output.write('Done.\n')

		output.write('\nnetselect(): returning %s and %s\n' % (top_hosts,
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
		
		output.write('netselect_split() got %s hosts.\n' % len(hosts), 2)
		
		host_blocks = self.host_blocks(hosts, block_size)
		
		output.write(' split into %s blocks\n' % len(host_blocks), 2)
		
		top_hosts = []
		ret_hosts = {}
		
		block_index = 0
		for block in host_blocks:
			output.print_info('Using netselect to choose the top '
			'%d hosts, in blocks of %s. %s of %s blocks complete.'
			% (number, block_size, block_index, len(host_blocks)))
			
			host_dict = self.netselect(block, len(block), quiet=True)[1]
			
			output.write('ran netselect(%s, %s), and got %s\n' % (block, len(block),
				host_dict), 2)
			
			for key in host_dict.keys():
				ret_hosts[key] = host_dict[key]
			block_index += 1
		
		sys.stderr.write('\rUsing netselect to choose the top'
		'%d hosts, in blocks of %s. %s of %s blocks complete.\n'
		% (number, block_size, block_index, len(host_blocks)))

		host_ranking_keys = ret_hosts.keys()
		host_ranking_keys.sort()

		for rank in host_ranking_keys[:number]:
			top_hosts.append(ret_hosts[rank])
		
		output.write('netselect_split(): returns %s\n' % top_hosts, 2)
		
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

		output.write('\n_host_blocks(): returns %s blocks, each about %s in size\n'
				% (len(host_array), len(host_array[0])), 2)

		return host_array


class Deep(object):
	"""handles deep mode mirror selection."""

	_bufsize = 4096

	def __init__(self, hosts, options):
		self.urls = []
		self._hosts = hosts
		self._number = options.servers
		self._dns_timeout = options.timeout
		self._connect_timeout = options.timeout
		self._download_timeout = options.timeout

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
			output.print_info('Downloading 100k files from each mirror... [%s of %s]'\
							% (prog, num_hosts) )
			
			mytime, ignore = self.deeptime(host, maxtime)

			if not ignore and mytime < maxtime:
				maxtime, top_hosts = self._list_add((mytime, host), \
						maxtime, top_hosts, self._number)
			else:
				continue
		
		output.write('deeptest(): got %s hosts, and returned %s\n' % (num_hosts, \
			str(top_hosts.values())), 2)
			
		output.write('\n')	#this just makes output nicer

		#can't just return the dict.valuse, because we want the fastest mirror first...
		keys = top_hosts.keys()
		keys.sort()

		rethosts = []
		for key in keys:
			rethosts.append(top_hosts[key])

		self.urls = rethosts


	def deeptime(self, url, maxtime):
		"""
		Takes a single url and fetch command, and downloads the test file.
		Can be given an optional timeout, for use with a clever algorithm.
		Like mine.
		"""
		output.write('\n_deeptime(): maxtime is %s\n' % maxtime, 2)
		
		if url.endswith('/'):	#append the path to the testfile to the URL
			url = url + 'distfiles/mirrorselect-test'
		else:
			url = url + '/distfiles/mirrorselect-test'

		url_parts = urlparse.urlparse(url)

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
			except socket.error, e:
				output.write('deeptime(): dns error for host %s: %s\n' % \
					(url_parts.hostname, e), 2)
			except TimeoutException:
				output.write('deeptime(): dns timeout for host %s\n' % \
					(url_parts.hostname,), 2)

		if not ips:
			output.write('deeptime(): unable to resolve ip for host %s\n' % \
				(url_parts.hostname,), 2)
			return (None, True)

		delta = 0
		f = None

		for ip in ips:
			try:
				ip_url = url.replace(url_parts.hostname, ip, 1)
				try:
					signal.alarm(self._connect_timeout)
					f = urllib.urlopen(ip_url)
					break
				finally:
					signal.alarm(0)
			except EnvironmentError, e:
				output.write(('deeptime(): connection to host %s ' + \
					'failed for ip %s: %s\n') % \
					(url_parts.hostname, ip, e), 2)
			except TimeoutException:
				output.write(('deeptime(): connection to host %s ' + \
					'timed out for ip %s\n') % \
					(url_parts.hostname, ip), 2)

		if f is None:
			output.write('deeptime(): unable to ' + \
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

		except EnvironmentError, e:
			output.write(('deeptime(): close connection to host %s ' + \
				'failed for ip %s: %s\n') % \
				(url_parts.hostname, ip, e), 2)
		except TimeoutException:
			output.write(('deeptime(): close connection to host %s ' + \
				'timed out for ip %s\n') % \
				(url_parts.hostname, ip), 2)

		try:

			# The first connection serves to "wake up" the route between
			# the local and remote machines. A second connection is used
			# for the timed run.
			try:
				signal.alarm(int(math.ceil(maxtime)))
				stime = time.time()
				f = urllib.urlopen(ip_url)
				while f.read(self._bufsize):
					pass
				delta = time.time() - stime
				f.close()
			finally:
				signal.alarm(0)

		except EnvironmentError, e:
			output.write(('deeptime(): download from host %s ' + \
				'failed for ip %s: %s\n') % \
				(url_parts.hostname, ip, e), 2)
			return (None, True)
		except TimeoutException:
			output.write(('deeptime(): download from host %s ' + \
				'timed out for ip %s\n') % \
				(url_parts.hostname, ip), 2)
			return (None, True)

		signal.signal(signal.SIGALRM, signal.SIG_DFL)

		output.write('deeptime(): download completed.\n', 2)
		output.write('deeptime(): %s seconds for host %s\n' % (delta, url), 2)
		return (delta, False)

	def _list_add(self, time_host, maxtime, host_dict, maxlen):
		"""
		Takes argumets ((time, host), maxtime, host_dict, maxlen)
		Adds a new time:host pair to the dictionary of top hosts.
		If the dictionary is full, the slowest host is removed to make space.
		Returns the new maxtime, be it the specified timeout, or the slowest host.
		"""
		if len(host_dict) < maxlen:	#still have room, and host is fast. add it.
			
			output.write('_list_add(): added host %s. with a time of %s\n' %
					(time_host[1], time_host[0]), 2)
			
			host_dict.update(dict([time_host]))
			times = host_dict.keys()
			times.sort()
			
		else: #We need to make room in the dict before we add. Kill the slowest.
			output.write('_list_add(): Adding host %s with a time of %s\n' %
					(time_host[1], time_host[0]), 2)
			times = host_dict.keys()
			times.sort()
			output.write('_list_add(): removing %s\n' % host_dict[times[-1]],
					2)
			del host_dict[times[-1]]
			host_dict.update(dict([time_host]))
			#done adding. now return the appropriate time
			times = host_dict.keys()
			times.sort()

		if len(host_dict) < maxlen:	#check again to choose new timeout
			output.write('_list_add(): host_dict is not full yet.'
					' reusing timeout of %s sec.\n' % maxtime, 2)
			retval = maxtime
		else:
			output.write('_list_add(): host_dict is full. Selecting the best'
			' timeout\n', 2)
			if times[-1] < maxtime:
				retval = times[-1]
			else:
				retval = maxtime

		output.write('_list_add(): new max time is %s seconds,'
				' and now len(host_dict)= %s\n' % (retval, len(host_dict)), 2)

		return retval, host_dict


class Interactive(object):
	"""Handles interactive host selection."""

	def __init__(self, hosts, options):
		self.urls = []

		self.interactive(hosts, options)
		output.write('Interactive.interactive(): self.urls = %s\n' % self.urls, 2)

		if len(self.urls[0]) == 0:
			sys.exit(1)
	
	
	def interactive(self, hosts, options):
		"""
		Some sort of interactive menu thingy.
		"""
		if options.rsync:
			dialog = 'dialog --stdout --title "Gentoo RSYNC Mirrors"'\
				' --radiolist "Please select your desired mirror:" 20 110 14'
		else:
			dialog = 'dialog --separate-output --stdout --title'\
				' "Gentoo Download Mirrors" --checklist "Please'\
				' select your desired mirrors:'
			if not options.ipv4 and not options.ipv6:
				dialog += '\n* = supports ipv6'

			dialog += '" 20 110 14'

		for (url, args) in sorted(hosts, key = lambda x: (x[1]['country'].lower(), x[1]['name'].lower()) ):
			marker = ""
			if (not options.ipv6 and not options.ipv4) and args['ipv6'] == 'y':
				marker = "* "
			if options.ipv6 and ( args['ipv6'] == 'n' ): continue
			if options.ipv4 and ( args['ipv4'] == 'n' ): continue
			if options.http and ( args['proto'] != 'http'): continue
			if options.ftp and ( args['proto'] != 'ftp'): continue

			dialog += ' ' + '"%s" "%s%s: %s" "OFF"' % ( url, marker, args['country'], args['name'] )

		mirror_fd = os.popen('%s' % codecs.encode(dialog, 'utf8'))
		mirrors = mirror_fd.read()
		mirror_fd.close()
		
		self.urls = mirrors.rstrip().split('\n')


def _have_bin(name):
	"""
	Determines whether a particular binary is available on the host system.
	"""
	for path_dir in os.environ.get("PATH", "").split(":"):
		if not path_dir:
			continue
		file_path = os.path.join(path_dir, name)
		if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
			return file_path
	return None


def handler(signum, frame):
	output.print_err('Caught signal %s. Exiting' % signum)

def write_config(hosts, out, path, sync=False):
	"""
	Writes the make.conf style string to the given file, or to stdout.
	"""
	if sync:
		var = 'SYNC'
	else:
		var = 'GENTOO_MIRRORS'
		
	mirror_string = '%s="%s"' % (var, ' '.join(hosts))

	if out:
		print
		print mirror_string
		sys.exit(0)


	output.write('\n')
	output.print_info('Modifying make.conf with new mirrors...\n')
	try:
		config = open(path, 'r')
		output.write('\tReading make.conf\n')
		lines = config.readlines()
		config.close()
		output.write('\tMoving to %s.backup\n' % path)
		shutil.move(path, path + '.backup')
	except IOError:
		lines = []
	
	regex = re.compile('^%s=.*' % var)
	for line in lines:
		if regex.match(line):
			lines.remove(line)
	
	lines.append(mirror_string)

	output.write('\tWriting new make.conf\n')
	config = open(path, 'w')
	for line in lines:
		config.write(line)
	config.write('\n')
	config.close()

	output.print_info('Done.\n')
	sys.exit(0)

def get_filesystem_mirrors(out, path, sync=False):
	"""
	Read the current mirrors and retain mounted filesystems mirrors
	"""
	fsmirrors = []

	if sync:
		var = 'SYNC'
	else:
		var = 'GENTOO_MIRRORS'
	
	try:
		f = open(path,'r')
	except IOError, e:
		return fsmirrors

	""" Search for 'var' in make.conf and extract value """
	try:
		lex = shlex.shlex(f, posix=True)
		lex.wordchars = string.digits+string.letters+"~!@#$%*_\:;?,./-+{}"
		lex.quotes = "\"'"
		while 1:
			key = lex.get_token()
			if key == var:
				equ = lex.get_token()
				
				if (equ == ''):
					break
				elif (equ != '='):
					break

				val = lex.get_token()
				if val is None:
					break

				""" Look for mounted filesystem in value """
				mirrorlist = val.rsplit()
				p = re.compile('rsync://|http://|ftp://', re.IGNORECASE)
				for mirror in mirrorlist:
					if (p.match(mirror) == None):
						fsmirrors.append(mirror)
				break
			elif key is None:
				break
	except Exception, e:
		fsmirrors = []

	return fsmirrors

def parse_args(argv):
	"""
	Does argument parsing and some sanity checks.
	Returns an optparse Options object.

	The descriptions, grouping, and possibly the amount sanity checking
	need some finishing touches.
	"""
	desc = "\n".join((
			output.white("examples:"),
			"",
			output.white("	 automatic:"),
			"		 # mirrorselect -s5",
			"		 # mirrorselect -s3 -b10 -o >> /mnt/gentoo/etc/make.conf",
			"		 # mirrorselect -D -s4",
			"",
			output.white("	 interactive:"),
			"		 # mirrorselect -i -r",
			))
	parser = OptionParser(
		formatter=ColoredFormatter(), description=desc,
		version='Mirrorselect version: %s' % __revision__)

	group = parser.add_option_group("Main modes")
	group.add_option(
		"-i", "--interactive", action="store_true", default=False,
		help="Interactive Mode, this will present a list "
		"to make it possible to select mirrors you wish to use.")
	group.add_option(
		"-D", "--deep", action="store_true", default=False,
		help="Deep mode. This is used to give a more accurate "
		"speed test. It will download a 100k file from "
		"each server. Because of this you should only use "
		"this option if you have a good connection.")

	group = parser.add_option_group(
		"Server type selection (choose at most one)")
	group.add_option(
		"-F", "--ftp", action="store_true", default=False,
		help="ftp only mode. Will not consider hosts of other "
		"types.")
	group.add_option(
		"-H", "--http", action="store_true", default=False,
		help="http only mode. Will not consider hosts of other types")
	group.add_option(
		"-r", "--rsync", action="store_true", default=False,
		help="rsync mode. Allows you to interactively select your"
		" rsync mirror. Requires -i to be used.")
	group.add_option(
		"-4", "--ipv4", action="store_true", default=False,
		help="only use IPv4")
	group.add_option(
		"-6", "--ipv6", action="store_true", default=False,
		help="only use IPv6")

	group = parser.add_option_group("Other options")
	group.add_option(
		"-o", "--output", action="store_true", default=False,
		help="Output Only Mode, this is especially useful "
		"when being used during installation, to redirect "
		"output to a file other than /etc/make.conf")
	group.add_option(
		"-b", "--blocksize", action="store", type="int",
		help="This is to be used in automatic mode "
		"and will split the hosts into blocks of BLOCKSIZE for "
		"use with netselect. This is required for certain "
		"routers which block 40+ requests at any given time. "
		"Recommended parameters to pass are: -s3 -b10")
	group.add_option(
		"-t", "--timeout", action="store", type="int",
		default="10", help="Timeout for deep mode. Defaults to 10 seconds.")
	group.add_option(
		"-s", "--servers", action="store", type="int", default=1,
		help="Specify Number of servers for Automatic Mode "
		"to select. this is only valid for download mirrors. "
		"If this is not specified, a default of 1 is used.")
	group.add_option(
		"-d", "--debug", action="store_const", const=2, dest="verbosity",
		default=1, help="debug mode")
	group.add_option(
		"-q", "--quiet", action="store_const", const=0, dest="verbosity",
		help="Quiet mode")

	if len(argv) == 1:
		parser.print_help()
		sys.exit(1)

	options, args = parser.parse_args(argv[1:])

	# sanity checks

	# hack: check if more than one of these is set
	if options.http + options.ftp + options.rsync > 1:
		output.print_err('Choose at most one of -H, -f and -r')

	if options.ipv4 and options.ipv6:
		output.print_err('Choose at most one of --ipv4 and --ipv6')

	if (options.ipv6 and not socket.has_ipv6) and not options.interactive:
		options.ipv6 = False
		output.print_err('The --ipv6 option requires python ipv6 support')

	if options.rsync and not options.interactive:
		output.print_err('rsync servers can only be selected with -i')

	if options.interactive and (
		options.deep or
		options.blocksize or
		options.servers > 1):
		output.print_err('Invalid option combination with -i')

	if (not options.deep) and (not _have_bin('netselect') ):
		output.print_err(
			'You do not appear to have netselect on your system. '
			'You must use the -D flag')
	
	if (os.getuid() != 0) and not options.output:
		output.print_err('Must be root to write to /etc/make.conf!\n')
	
	if args:
		output.print_err('Unexpected arguments passed.')

	# return results
	return options


output = Output()	#the only FUCKING global. Damnit.
def main(argv):
	"""Lets Rock!"""
	config_path = '/etc/make.conf'

	signal.signal(signal.SIGINT, handler)

	options = parse_args(argv)
	output.verbosity = options.verbosity

	fsmirrors = get_filesystem_mirrors(options.output, config_path, options.rsync)
	if options.rsync:
		hosts = Extractor(MIRRORS_RSYNC_DATA, options).hosts
	else:
		hosts = Extractor(MIRRORS_3_XML, options).hosts

	if options.interactive:
		selector = Interactive(hosts, options)
	elif options.deep:
		selector = Deep(hosts, options)
	else:
		selector = Shallow(hosts, options)

	write_config(fsmirrors + selector.urls, options.output, config_path, options.rsync)


if __name__ == '__main__':
	main(sys.argv)
