#!/usr/bin/env python
import argparse
import sys
from pathlib import Path
import collections
from .command_runner import check_and_update_files, ReadmeCommandError


def main():
    parser = argparse.ArgumentParser(
        "readme-commands", description="Executes shell commands in markdown files"
    )
    parser.add_argument(
        "files",
        type=Path,
        nargs="*",
        help="File(s) to work on",
    )
    parser.add_argument(
        "-f", "--fix", action="store_true", help="If true, files are over-written"
    )
    args = parser.parse_args()
    if not args.files:
        print("Warning: no files provided")

    stats = collections.Counter()
    try:
        files_updated = check_and_update_files(args.files, fix=args.fix, stats=stats)
    except ReadmeCommandError as e:
        sys.exit(str(e))

    # either print about success, or exit reporting the fixes
    n_files_4_msg = len(files_updated) or len(args.files)
    some_files = "1 file" if n_files_4_msg == 1 else f"{n_files_4_msg} files"
    some_blocks = "1 block" if stats["blocks"] < 2 else f"{stats['blocks']} blocks"
    action = "are incorrect" if not args.fix else "were updated"
    if files_updated:
        sys.exit(
            f"File contents {action} for {some_files}: "
            f"{', '.join(str(el) for el in files_updated)}"
        )
    else:
        print(
            f"Ran `readme-commands` on {some_blocks} in {some_files}; no changes made."
        )


if __name__ == "__main__":
    main()
