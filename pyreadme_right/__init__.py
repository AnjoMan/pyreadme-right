#!/usr/bin/env python
from importlib.resources import files

__version__ = files(__name__).joinpath("VERSION").open("r").read().strip()
