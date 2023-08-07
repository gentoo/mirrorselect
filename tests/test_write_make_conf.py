# Copyright 2019 Gentoo Authors

import os
import shutil
import tempfile
import unittest

from mirrorselect.configs import write_make_conf
from mirrorselect.output import Output


class WriteMakeConfTestCase(unittest.TestCase):
    def test_write_make_conf(self):
        def __do_it(var, mirror_string, make_conf, expected_result):
            tempdir = tempfile.mkdtemp()
            status_output = open(os.devnull, "w")
            # print("------make_conf--------", make_conf, "----------------------")
            # print("*****expect*****\n", expected_result, "***********")
            try:
                config_path = os.path.join(tempdir, "make.conf")
                with open(config_path, "w") as f:
                    f.write(make_conf)
                write_make_conf(
                    Output(out=status_output), config_path, var, mirror_string
                )
                with open(config_path) as f:
                    result = f.read()
                    # print("!!!result!!!\n", result, "!!!!!!!!!!\n")
                self.assertEqual(result, f"{expected_result}".format(mirror_string))
            finally:
                shutil.rmtree(tempdir)
                status_output.close()

        var = "GENTOO_MIRRORS"
        mirrors = (
            (f'{var}="a"'),
            (f'{var}="a b"'),
            (f'{var}="a b c"'),
        )

        cases = (
            (f'{var}="foo\nbar"\n', "{}\n"),
            (f'\n{var}="foo\nbar"\n', "\n{}\n"),
            (f'\n{var}="foo bar"\n', "\n{}\n"),
            (f'\n{var}="foo bar"\n\n', "\n\n{}\n"),
            (f'\n{var}="foo \\\nbar"\n', "\n{}\n"),
            (f'\n\n{var}="foo \\\nbar"\n', "\n\n{}\n"),
            (f'\n\n{var}="foo \\\nbar"\na="b"\n', '\n\na="b"\n{}\n'),
            (f'\n\n{var}="foo \\\n    bar"\na="b"\n', '\n\na="b"\n{}\n'),
            (
                f'\n\n{var}="foo \\\n    bar\\\n    baz"\na="b"\n',
                '\n\na="b"\n{}\n',
            ),
            ("", "{}\n"),
        )

        for mirror in mirrors:
            for make_conf, expected_result in cases:
                __do_it(var, mirror, make_conf, expected_result)
