import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def target_file(file_contents):
    with tempfile.TemporaryDirectory() as working_dir:
        target_file = Path(working_dir) / "file.md"
        with open(target_file, "w") as f:
            f.write(file_contents)
        yield target_file


SCRIPT = "readme-right"

# some features of this test file:
#  * there is whitespace to preserve between the commands
#  * the command outputs are portable / replicable ('echo $(date)' would be a dumb test)
#  * there are more than one command
CORRECT_FILE_EXPECTATION = """\
# README for testing

here is a command block:

```readme-commands
$ echo "Foo"
Foo

$ echo "Bar"
Bar
```

"""
BAD_FILE_CONTENTS = """\
# README for testing

here is a command block:

```readme-commands
$ echo "Foo"
"I'm a teapot"

$ echo "Bar"
"a peanut walked into one and was a-salted!"
```

"""


@pytest.mark.parametrize("file_contents", [CORRECT_FILE_EXPECTATION])
def test_readme_command_leaves_good_files_unchanged(target_file):
    first_modified_time = os.path.getmtime(target_file)

    result = subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the script to exit successfully, printing info
    console = result.stdout.decode()
    assert "Ran `readme-commands` blocks in 1 file; no changes made." in console

    # we expect the file to match the contents it was made with
    with open(target_file) as f:
        corrected_file_contents = f.read()
    assert corrected_file_contents == CORRECT_FILE_EXPECTATION

    # we expect the file never to have been written to
    assert os.path.getmtime(target_file) == first_modified_time


@pytest.mark.parametrize("file_contents", [BAD_FILE_CONTENTS])
def test_readme_command_fixes_bad_files(target_file):
    first_modified_time = os.path.getmtime(target_file)

    result = subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the file was written to
    assert os.path.getmtime(target_file) > first_modified_time

    # we expect the script to exit with a nonzero error code, printing info
    # to stderr
    console = escape_ansi(result.stderr.decode())
    assert re.search(
        r"File contents were updated for 1 file: (/\w+)+/file\.md", console
    )

    # we expect the file to have been fixed
    with open(target_file) as f:
        corrected_file_contents = f.read()
    assert corrected_file_contents == CORRECT_FILE_EXPECTATION


FILE_WITH_MIXED_COMMANDS = """\
# README for testing

here is a command block:

```readme-commands
>>> import math
>>> math.sqrt(25)
5
$ python --version
>>> math.sqrt(25)
```
"""


@pytest.mark.parametrize("file_contents", [FILE_WITH_MIXED_COMMANDS])
def test_mixed_commands_are_rejected(target_file):
    """we're forcing users to pick shell or python commands, but not mix them"""
    result = subprocess.run([SCRIPT, target_file], capture_output=True)

    # we expect the script to exit with a nonzero error code, printing info
    # to stderr
    print(result)
    console = escape_ansi(result.stderr.decode())
    print(console)

    # assert the file name is reported
    assert re.search(r"Error in (/\w+)+/file\.md;", console)
    # assert position in the file is reported
    assert "readme-commands block at (ln 5, col 1);" in console
    # assert error is described
    assert " shell ($ ) and python (>>> ) commands cannot be mixed"

    # assert erroneous commands are printed out and highlighted with blocks
    assert (
        """\
 >>> import math
 >>> math.sqrt(25)
 5
⁍$ python --version
 >>> math.sqrt(25)
"""
        in console
    )


def escape_ansi(line):
    """Its really annoying to test these are in the output, so we strip them out to do
    string assertions"""
    ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]")
    return ansi_escape.sub("", line)


MULTIPLE_BLOCKS_CONTENTS = """\

here is a shell block:

```readme-commands
$ echo "Knock Knock"
Knock Knock
$ echo "Who's there?"
i don't know!
```
There are lots of things you'd want
to do with a shell block,
such as try to run the document --help
to see the man page, or show
an example of how the output will look when
running a command. However, you might
also want to show off parts of a python interface
so that its obvious how to use the code more programmatically,
and this could be done using python commands.
The point of writing this long explanation about what
you might want to do with this is just that it should
make `difflib` split up the information about
what was fixed into two different segments; if we
didn't say a lot of meaningless stuff here
then this would not happen and it wouldn't be as obvious
how things work. But we are saying all this stuff,
and so it will get split up.

here is a python block:
```readme-commands
>>> import math
>>> math.sqrt(25)
```

"""


@pytest.mark.parametrize("file_contents", [MULTIPLE_BLOCKS_CONTENTS])
def test_readme_command_handles_multiple_blocks(target_file):
    """We're checking that a file can have more than one block; we're also asserting
    that the cli prints out diffs describing what in each file was changed"""
    result = subprocess.run([SCRIPT, target_file, "--dry-run"], capture_output=True)
    console = escape_ansi(result.stderr.decode())
    difference = """\
--- committed
+++ correct
@@ -5,7 +5,7 @@
 $ echo "Knock Knock"
 Knock Knock
 $ echo "Who's there?"
-i don't know!
+Who's there?
 ```
 There are lots of things you'd want
 to do with a shell block,
@@ -29,5 +29,6 @@
 ```readme-commands
 >>> import math
 >>> math.sqrt(25)
+5.0"""
    assert difference in console


@pytest.mark.parametrize("file_contents", [BAD_FILE_CONTENTS])
def test_readme_skips_modifications_in_dry_run(target_file):
    first_modified_time = os.path.getmtime(target_file)

    result = subprocess.run([SCRIPT, target_file, "--dry-run"], capture_output=True)

    # we expect the file was not written to
    assert os.path.getmtime(target_file) == first_modified_time

    # we expect the script to exit with a nonzero error code, printing info
    # to stderr
    console = result.stderr.decode()
    assert re.search(
        r"File contents are incorrect for 1 file: (/\w+)+/file\.md", console
    )

    # we expect the file to have its bad contents still
    with open(target_file) as f:
        corrected_file_contents = f.read()
    assert corrected_file_contents == BAD_FILE_CONTENTS
