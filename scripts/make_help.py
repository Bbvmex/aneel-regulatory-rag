"""Print Makefile targets annotated with '## '; portable across cmd, PowerShell and sh."""

import re
import sys

TARGET = re.compile(r"^([a-zA-Z_-]+):.*?## (.*)$")

for makefile in sys.argv[1:]:
    with open(makefile, encoding="utf-8") as fh:
        for line in fh:
            if match := TARGET.match(line):
                print(f"  {match.group(1):<12} {match.group(2)}")
