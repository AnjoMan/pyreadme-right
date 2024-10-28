#!/usr/bin/env python
import difflib
import re
import subprocess
import sys
from pathlib import Path
from pprint import pformat
from re import Match
import collections
from typing import Dict, List
import io
from contextlib import redirect_stdout

__all__ = ["check_and_update_files"]

# we are finding whatever is inside ```readme-commands<>```
README_COMMAND = re.compile(r"\`\`\`readme-commands[\n\r]+(?P<body>[^\`]+)\`\`\`")

# we are finding matches for $ <command> that are at the start of the line, including
# any empty lines preceeding them so we can preserve whitespace separating commands
SHELL_COMMAND = re.compile(r"^[\r\n]*\$ +(?P<command>[^\n\r]+)", flags=re.MULTILINE)
PYTHON_COMMAND = re.compile(r"^[\r\n]*\>>> (?P<command>[^\n\r]+)", flags=re.MULTILINE)


def check_and_update_files(
    files: List[Path], fix: bool = False, stats: collections.Counter = None
) -> List[Path]:
    """For each file, runs the commands and compares the output to see if the files are
    correct"""

    files_updated = []
    _stats = stats or collections.Counter()
    for readme_file_name in files:
        with open(readme_file_name, "r") as f:
            existing_readme_contents = f.read()

        try:
            new_readme_contents = execute_readme_commands(
                existing_readme_contents, stats
            )
        except ReadmeCommandError as e:
            raise ReadmeCommandError(
                f"Error in {bcolors.BOLD}{readme_file_name}{bcolors.ENDC}; {str(e)}"
            ) from None

        if new_readme_contents != existing_readme_contents:
            log_diff(existing_readme_contents, new_readme_contents)
            files_updated.append(readme_file_name)
            if fix:
                with open(readme_file_name, "w") as f:
                    # we'll overwrite the file contents so the user can just commit them
                    # if they are acceptable (similar to black pre-commit hook)
                    f.write(new_readme_contents)
    return files_updated


def execute_readme_commands(
    readme_contents: str, stats: collections.Counter = None
) -> str:
    """Finds readme-commands blocks in the provided content, executes them, and updates
    the block with the command stdout


    e.g given

        Here is an example of how to identify your local version of python:
        ```readme-commands
        $ python --version
        ```

    the function might return

        Here is an example of how to identify your local version of python:
        ```readme-commands
        $ python --version
        3.10.9
        ```


    """
    replacements: Dict[Match, str] = {}
    _stats = stats if stats is not None else collections.Counter()
    for block_match in README_COMMAND.finditer(readme_contents):
        _stats["blocks"] += 1
        try:
            replacement_body = handle_command_block(block_match)
        except ReadmeCommandError as e:
            raise ReadmeCommandError(
                "readme-commands block at "
                f"{index_to_coordinates(readme_contents, block_match.start())}; "
                f"{str(e)}"
            ) from None
        replacements[block_match] = f"```readme-commands\n{replacement_body}```"
    return replace_matches_with_text(replacements, readme_contents)


def handle_command_block(block_match: Match) -> str:
    """Finds python / shell commands in the block and assembles the shell output of
    running them.

    Commands are expected to match a regex with a preceding string '>>> ' or '$ ',
    and will be included in the output so that it looks like what a user would see in
    their shell; e.g.:

        $ python --version
        $ echo "I'm running $(python --version)"

    results in

        $ python --version
        Python 3.10.9
        $ echo "I'm running $(python --version)"
        I'm running Python 3.10.9

    This function handles both python and shell commands, and rejects mixing the two.
    """
    python_commands = list(PYTHON_COMMAND.finditer(block_match["body"]))
    shell_commands = list(SHELL_COMMAND.finditer(block_match["body"]))

    # error handling for mixed commands:
    if python_commands and shell_commands:
        details = make_bad_commands_detail(block_match, python_commands, shell_commands)
        raise ReadmeCommandError(
            f"shell ($ ) and python (>>> ) commands cannot be mixed:\n{details}"
        )

    if python_commands:
        return handle_python_commands(python_commands)
    else:
        return handle_shell_commands(shell_commands)


def handle_shell_commands(shell_commands: List[Match]) -> str:
    """Executes shell commands and stiches together commands with output"""
    retval = ""
    for command_match in shell_commands:
        command_result = subprocess.run(
            command_match["command"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
        )
        printout = command_result.stdout.decode()
        printerr = command_result.stderr.decode()

        retval += f"{command_match[0]}\n{printout or printerr}"
    return retval


def handle_python_commands(python_commands: List[Match]) -> str:
    """Executes python commands and stitches together commands with output

    Commands are expected to be written like they would be in a python interpreter:
        >>> from math import sqrt
        >>> sqrt(1+2)

    This function evaluates (or executes, if that fails) the stuff after >>>, collects
    any printable results and adds them to the script. the example would return

        >>> from math import sqrt
        >>> sqrt(1+2)
    1.7320508075688772

    Note: it is important to execute all the commands in the same context so that any
    locals they create are persisted across commands; if we e.g. do each command in a
    function, variables and imports could not be shared
    """
    retval = ""
    globals = {}
    locals = {}
    for command_match in python_commands:
        command_text = command_match["command"]
        try:
            try:
                # first we try to eval; if the command is an expression (e.g. >>> 1 + 2)
                # we'll capture the results
                command_result = (
                    f"\n{eval(command_text, globals=globals, locals=locals)}"
                )
            except SyntaxError:
                # eval only does expressions; we want to be able to also run statements
                # (e.g. '>>> import package' or '>>> x = 1+2') and capture any stdout they
                # create (e.g. '>>> print(1+2)'' )
                try:
                    out = io.StringIO()
                    with redirect_stdout(out):
                        exec(command_text, globals=globals, locals=locals)
                    command_result = out.read()
                except SyntaxError as e:
                    command_result = f"\n*** {type(e).__name__}: {str(e)}"
        except Exception as e:
            command_result = f"\n*** {type(e).__name__}: {str(e)}"

        if command_result is None:
            printout = ""  # we don't want to print out "None" since interpreters don't
        elif isinstance(command_result, str):
            printout = f"{command_result}\n"
        else:
            printout = f"{pformat(command_result)}\n"

        retval += f"{command_match[0].rstrip()}{str(printout)}"
    return retval


def replace_matches_with_text(replacements: Dict[Match, str], markdown) -> str:
    """Replaces matched text in `markdown` with contents of `replacements`"""
    if not replacements:
        return markdown

    finds = list(replacements.keys())

    # first we split the doc up into segments abutting matches in 'replacements.keys()'
    segments = [
        markdown[0 : finds[0].start()],
        *[
            markdown[finda.end() : findb.start()]
            for finda, findb in zip(finds[:-1], finds[1:])
        ],
        markdown[finds[-1].end() :],
    ]

    # second, we stitch the document back together, interleaving the segments and
    # replacement text
    updated_markdown = "".join(
        f"{preceeding_segment}{replacement}"
        for preceeding_segment, replacement in zip(
            segments[0:-1], replacements.values()
        )
    )
    updated_markdown += f"{segments[-1]}"
    return updated_markdown


# error / IO stuff:


class ReadmeCommandError(ValueError):
    """An error we can raise when we're sure the problem is with a users inputs.

    If any code handling a block or command fails with this error, we assume we can
    catch it and re-raise the error adding in context about user data while dropping
    stack-trace information, since there is nothing about the implementation of
    readme-commands that is relevant."""

    ...


def index_to_coordinates(string: str, index: int) -> str:
    """Returns (ln x, col y) describing the position of 'index' in 'string'"""
    if not len(string):
        sp = [[1]]
    else:
        sp = string[: index + 1].splitlines(keepends=True)
    return f"{bcolors.BOLD}(ln {len(sp)}, col {len(sp[-1])}){bcolors.ENDC}"


class bcolors:
    """captures some basic ansi escape colours for doing coloured text;

    usage: bcolors.OKGREEN + "highlighted text" + bcolors.ENDC
           f"only the {bcolors.OKGREEN}highlighted text{bcolors.ENDC} will be green"
    """

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def color_green(match: Match):
    return bcolors.OKGREEN + match[0] + bcolors.ENDC


def color_red(match: Match):
    return bcolors.FAIL + match[0] + bcolors.ENDC


def log_diff(old_contents: str, new_contents: str):
    """creates a git-like diff between old/new contents, for human consumption, and logs
    to stderr"""
    diff = difflib.unified_diff(
        old_contents.splitlines(),
        new_contents.splitlines(),
        fromfile="committed",
        tofile="correct",
    )
    diff_str = "\n".join([el.strip("\n") for el in diff])
    # difflib puts + infront of added and - infront of subtracted text; we'll highlight
    # those green / red
    diff_str = re.sub(r"^\+{1}.*$", color_green, diff_str, flags=re.MULTILINE)
    diff_str = re.sub(r"^-{1}.*$", color_red, diff_str, flags=re.MULTILINE)
    sys.stderr.write(diff_str)


def make_bad_commands_detail(
    block_match: Match, python_commands: List[Match], shell_commands: List[Match]
) -> str:
    """sorts out which commands to highlight as invalid, and uses color + blocking text
    to highlight them

        e.g given matches in this block of text:
            >>> import math
            >>> math.sqrt(25)
            5
            $ python --version
            >>> math.sqrt(25)

        returns

             >>> import math
             >>> math.sqrt(25)
             5
            ⁍$ python --version
             >>> math.sqrt(25)
    """

    # if the first command is a shell command, python is not allowed (and vise-versa)
    valid_commands, invalid_commands = (
        (python_commands, shell_commands)
        if python_commands[0].start() < shell_commands[0].start()
        else (shell_commands, python_commands)
    )

    # colour the commands and put them back in the text
    replacements = {command: color_red(command) for command in invalid_commands}
    coloured_highlights = replace_matches_with_text(replacements, block_match["body"])

    # add preceeding blocks in case of colorblindness
    detail = "\n".join(
        (f"{color_red('⁍')}{line}" if "\x1b[" in line else f" {line}")
        for line in coloured_highlights.splitlines()
    )
    return detail
