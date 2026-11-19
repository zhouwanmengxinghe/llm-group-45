"""Restore one-line unittest statuses while preserving actual outcomes."""
import re


def normalize_unittest_output(text):
    lines = []
    pending = None
    for line in text.splitlines():
        header = re.match(r"^(test\S+ \([^)]+\))(?:\s*\.\.\..*)?$", line)
        if header:
            pending = header.group(1)
        status = re.search(r"(?:\.\.\.\s+|^)(ok|OK|FAIL|ERROR|skipped.*)$", line)
        if pending and status:
            canonical = pending + " ... " + status.group(1)
            if line != canonical:
                lines.append(line)
            line = canonical
            pending = None
        lines.append(line)
    return "\n".join(lines) + "\n"
