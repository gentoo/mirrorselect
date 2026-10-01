# Copyright 2019-2026 Gentoo Authors

import os
import shutil
import tempfile
import unittest

from mirrorselect.configs import DistfilesConfig
from mirrorselect.output import Output

mirror_line = "GENTOO_MIRRORS = https://example.com"

class MakeConfSubdirTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.status_output = open(os.devnull, "w")
        self.output = Output(out=self.status_output)

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        self.status_output.close()

    def make_path(self, *fragment: str):
        return os.path.join(self.tempdir, *fragment)

    def test_make_conf_single_file(self):
        os.mkdir(self.make_path("portage"))
        config_path = self.make_path("portage", "make.conf")

        with open(config_path, "w") as f:
            f.write(mirror_line)

        sut = DistfilesConfig(self.tempdir)
        result = sut.get_conf_path(self.output)
        self.assertEqual(result, self.make_path("portage/make.conf"))


    def test_make_conf_subdir_with_mirrors(self):
        os.mkdir(self.make_path("portage"))
        os.mkdir(self.make_path("portage", "make.conf"))
        config_path = self.make_path("portage", "make.conf", "base")

        with open(config_path, "w") as f:
            f.write(mirror_line)

        sut = DistfilesConfig(self.tempdir)
        result = sut.get_conf_path(self.output)
        self.assertEqual(result, self.make_path("portage/make.conf/base"))


    def test_make_conf_subdir_without_mirrors(self):
        os.mkdir(self.make_path("portage"))
        os.mkdir(self.make_path("portage", "make.conf"))
        config_path = self.make_path("portage", "make.conf", "base")

        with open(config_path, "w") as _:
            # create an empty file
            pass

        sut = DistfilesConfig(self.tempdir)
        result = sut.get_conf_path(self.output)
        self.assertEqual(result, self.make_path("portage/make.conf/mirrorselect.conf"))

