# pyreadme-right

A script to run README.md examples and verify their output

```readme-commands
>>> import math
>>> math.sqrt(25)
5.0
```

It can be used via pre-commit or tests to ensure that any changes
you make to your code don't break examples that you gave in your
readme document.

## cli

The command line interface allows you to run the tool against a file, so you
can write your code directly in the

```readme-commands
$ readme-right --help
usage: readme-commands [-h] [-f] [files ...]

Executes shell commands in markdown files

positional arguments:
  files       File(s) to work on

options:
  -h, --help  show this help message and exit
  -f, --fix   If true, files are over-written
```

## pre-commit

`pyreadme-right` exposes a pre-commit hook, which you can use by doing

```yaml
# .pre-commit-config.yaml

repos:
  - repo: https://github.com/AnjoMan/pyreadme-right
    rev: 0.1.0
    hooks:
      - id: readme-commands
        args: ["--fix"]

```

When you do this, the tool will run against your README.md; if any code blocks don't produce the output
the file says they should, the step fails. You can optionally have the fixes written to the file, or just logged for you to manually fix.

## security

Note that `pyreadme-right` runs whatever code is present in the input file; this
is extremely unsecure if the file is not trusted (e.g. if it is user input) and
could lead to arbitary code execution if called in an unsafe way.
