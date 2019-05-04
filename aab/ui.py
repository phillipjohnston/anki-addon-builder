#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Anki Add-on Builder
#
# Copyright (C)  2016-2019 Aristotelis P. <https://glutanimate.com/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version, with the additions
# listed at the end of the license file that accompanied this program.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# NOTE: This program is subject to certain additional terms pursuant to
# Section 7 of the GNU Affero General Public License.  You should have
# received a copy of these additional terms immediately following the
# terms and conditions of the GNU Affero General Public License that
# accompanied this program.
#
# If not, please request a copy through one of the means of contact
# listed here: <https://glutanimate.com/contact/>.
#
# Any modifications to this file must keep this entire header intact.

"""
UI Compilation
"""

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import shutil
import logging
import re
from pathlib import Path
from datetime import datetime

from whichcraft import which

from . import PATH_DIST, __title__, __version__
from .config import Config
from .utils import relpath, call_shell, unicode

_template_header = '''\
# -*- coding: utf-8 -*-
#
# {display_name} Add-on for Anki
# Copyright (C)  {years} {author} <{contact}>
#
# This file was automatically generated by {__title__} v{__version__}
# It is subject to the same licensing terms as the rest of the program
# (see the LICENSE file which accompanies this program).
#
# WARNING! All changes made in this file will be lost!

"""
Initializes generated Qt forms/resources
"""\
'''

_template_all = """\
__all__ = [
{}
]\
"""

class UIBuilder(object):

    _re_munge = re.compile(r"^import .+?_rc(\n)?$", re.MULTILINE)
    _pyqt_version = {
        "anki21": "5",
        "anki20": "4"
    }
    _types = {
        "forms": {
            "pattern": "*.ui",
            "tool": "pyuic",
            "post_build": "_munge_form",
            "suffix": ""
        },
        "resources": {
            "pattern": "*.qrc",
            "tool": "pyrcc",
            "post_build": None,
            "suffix": "_rc"
        }
    }

    def __init__(self, root=None):
        self._root = root or PATH_DIST
        self._config = Config()
        gui_path = self._root / "src" / self._config["module_name"] / "gui"
        self._paths = {
            "forms": {
                "in": self._root / "designer",
                "out": gui_path / "forms"
            },
            "resources": {
                "in": self._root / "resources",
                "out": gui_path / "resources"
            }
        }
        self._format_dict = self._get_format_dict()

    def build(self, target="anki21"):
        logging.info("Starting UI build tasks for target %r...", target)

        for filetype, paths in self._paths.items():
            path_in = paths["in"]
            path_out = paths["out"] / target
            if not path_in.exists():
                logging.warning("No Qt %s folder found. Skipping build.",
                                filetype)
                continue
            self._build(filetype, path_in, path_out, target)

        logging.info("Done will all UI build tasks.")

    def _build(self, filetype, path_in, path_out, target):
        settings = self._types[filetype]

        # Basic checks

        tool = "{tool}{nr}".format(tool=settings["tool"],
                                   nr=self._pyqt_version[target])
        if which(tool) is None:
            logging.error("%s not found. Skipping %s build.", tool, tool)
            return False

        ui_files = list(path_in.glob(settings["pattern"]))
        if not ui_files:
            logging.warning("No %s found in %s. Skipping %s build.",
                            filetype, path_in, tool)
            return False

        logging.info("Building files in '%s' to '%s' with '%s'",
                     relpath(path_in), relpath(path_out), tool)

        # Cleanup

        logging.debug("Cleaning up old %s...", filetype)
        if path_out.exists():
            shutil.rmtree(unicode(path_out))
        path_out.mkdir(parents=True)

        # UI build loop

        if settings["post_build"]:
            post_build = getattr(self, settings["post_build"], None)
        else:
            post_build = None

        suffix = settings["suffix"]
        modules = []

        for in_file in ui_files:
            stem = in_file.stem
            new_stem = stem + suffix
            out_file = Path(path_out / new_stem).with_suffix(".py")

            logging.debug("Building element '%s'...", new_stem)
            # Use relative paths to improve readability of form header:
            cmd = "{tool} {in_file} -o {out_file}".format(
                tool=tool,
                in_file=relpath(in_file),
                out_file=relpath(out_file))
            call_shell(cmd)

            if post_build:
                post_build(out_file)

            modules.append(new_stem)

        # Last steps

        self._write_init_file(modules, path_out)

        logging.debug("Done with %s.", filetype)
        return True

    def _get_format_dict(self):
        config = self._config

        start_year = self._config.get("copyright_start")
        now = datetime.now().year
        if start_year and start_year != now:
            years = "{start_year}-{now}".format(start_year=start_year,
                                                now=now)
        else:
            years = "{now}".format(now=now)

        format_dict = {
            "display_name": config["display_name"],
            "author": config["author"],
            "contact": config["contact"],
            "__title__": __title__,
            "__version__": __version__,
            "years": years,
        }

        return format_dict

    def _write_init_file(self, modules, path_out):
        logging.debug("Generating init file for %s", relpath(path_out))

        header = _template_header.format(**self._format_dict)
        all_str = self._generate_all_str(modules)
        import_str = self._generate_import_str(modules)

        init = "\n\n".join((header, all_str, import_str)) + "\n"

        with (path_out / "__init__.py").open("w", encoding="utf-8") as f:
            f.write(init)

    def _generate_all_str(self, modules):
        module_string = ",\n".join('    "{}"'.format(m) for m in modules)
        out = _template_all.format(module_string)
        return out

    def _generate_import_str(self, modules):
        out = "\n".join('from . import {}'.format(m) for m in modules)
        return out

    def _munge_form(self, path):
        """
        Munge generated form to remove resource imports
        (I prefer to initialize these manually)
        """
        logging.debug("Munging %s...", relpath(path))
        with path.open("r+", encoding="utf-8") as f:
            form = f.read()
            munged = self._re_munge.sub("", form)
            f.seek(0)
            f.write(munged)
            f.truncate()