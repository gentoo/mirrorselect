# Copyright 2019 Gentoo Authors

import os
import shutil
import tempfile
import unittest

from mirrorselect.configs import write_make_conf
from mirrorselect.output import Output


class WriteMakeConfTestCase(unittest.TestCase):
	def test_write_make_conf(self):

		var = 'GENTOO_MIRRORS'
		mirror_string = '{}="a b"'.format(var)

		cases = (
			('{}="foo\nbar"\n'.format(var), '{}\n'.format(mirror_string)),
			('\n{}="foo\nbar"\n'.format(var), '\n{}\n'.format(mirror_string)),
			('\n{}="foo bar"\n'.format(var), '\n{}\n'.format(mirror_string)),
			('\n{}="foo bar"\n\n'.format(var), '\n\n{}\n'.format(mirror_string)),
			('\n{}="foo \\\nbar"\n'.format(var), '\n{}\n'.format(mirror_string)),
			('\n\n{}="foo \\\nbar"\n'.format(var), '\n\n{}\n'.format(mirror_string)),
			('\n\n{}="foo \\\nbar"\na="b"\n'.format(var), '\n\na="b"\n{}\n'.format(mirror_string)),
		)

		for make_conf, expected_result in cases:
			tempdir = tempfile.mkdtemp()
			status_output = open(os.devnull, 'w')
			try:
				config_path = os.path.join(tempdir, 'make.conf')
				with open(config_path, 'wt') as f:
					f.write(make_conf)
				write_make_conf(Output(out=status_output), config_path, var, mirror_string)
				with open(config_path, 'rt') as f:
					result = f.read()
				self.assertEqual(result, expected_result)
			finally:
				shutil.rmtree(tempdir)
				status_output.close()
