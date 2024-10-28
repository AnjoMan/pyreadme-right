import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def target_file(file_contents):
    """Creates a file with `file_contents` in a temp directory, and yields the
    file name"""
    with tempfile.TemporaryDirectory() as td:
        target_file = Path(td) / "file.md"
        with open(target_file, "w") as f:
            f.write(file_contents)
        yield target_file


SCRIPT = "pyreadme_right/__main__.py"
CORRECT_FILE_EXPECTATION = """\
# README for testing

here is a command block:

```readme-commands
>>> from math import sqrt
>>> x = 1; y = 2
>>> sqrt(x + y)
1.7320508075688772
```

"""
BAD_FILE_CONTENTS = """\
# README for testing

here is a command block:

```readme-commands
>>> from math import sqrt
>>> x = 1; y = 2
>>> sqrt(x + y)
```

"""


@pytest.mark.parametrize("file_contents", [CORRECT_FILE_EXPECTATION])
def test_readme_command_does_not_fix_good_files(target_file):
    first_modified_time = os.path.getmtime(target_file)

    result = subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the file not to be modified
    assert os.path.getmtime(target_file) == first_modified_time

    # we expect the script to exit successfully, printing info
    console = result.stdout.decode()
    assert "Ran `readme-commands` blocks in 1 file; no changes made." in console

    # we expect the file to match the contents it had before
    with open(target_file) as f:
        corrected_file_contents = f.read()
    assert corrected_file_contents == CORRECT_FILE_EXPECTATION


@pytest.mark.parametrize("file_contents", [BAD_FILE_CONTENTS])
def test_readme_command_fixes_bad_files(target_file):
    first_modified_time = os.path.getmtime(target_file)

    result = subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the file to have been modified
    assert os.path.getmtime(target_file) > first_modified_time

    # we expect the script to exit with a nonzero error code, printing info
    # to stderr
    console = result.stderr.decode()
    assert re.search(
        r"File contents were updated for 1 file: (/\w+)+/file\.md", console
    )
    # we expect the file to have been fixed
    with open(target_file) as f:
        corrected_file_contents = f.read()
    assert corrected_file_contents == CORRECT_FILE_EXPECTATION


FILE_WITH_EXCEPTIONS = """\
# README for testing

here is a command block:

```readme-commands
>>> import math

>>> math.sqrt(-1)
1
>>> f = lambda x 2*x
<lambda function id=23049238>
```
"""


@pytest.mark.parametrize("file_contents", [FILE_WITH_EXCEPTIONS])
def test_readme_python_handles_exceptions(target_file):
    """We want to make sure its possible to do exceptions in our readmes, both for the
    purposes of having good code blocks and so that if a user accidentally writes bad
    code, they see why their command output is wrong"""
    subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the exception outcomes are written to the file
    with open(target_file) as f:
        corrected_file_contents = f.read()

    expected_contents = """\
# README for testing

here is a command block:

```readme-commands
>>> import math

>>> math.sqrt(-1)
*** ValueError: math domain error
>>> f = lambda x 2*x
*** SyntaxError: invalid syntax (<string>, line 1)
```
"""
    assert corrected_file_contents == expected_contents
