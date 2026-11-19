"""Keep raw test logs on disk; give the model stable diagnostic excerpts."""
import re


def stable_log(text: str) -> str:
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"(?m)^([= ]*(?:\d+\s+(?:failed|passed|skipped|xfailed|xpassed|warnings?)[, ]*)+in )\d+(?:\.\d+)?(?:s\b| seconds\b)", r"\1<duration>s", text)
    text = re.sub(r"(?m)^(Ran \d+ tests? in )\d+(?:\.\d+)?s\b", r"\1<duration>s", text)
    text = re.sub(r"(tests finished:.*?, in )\d+(?:\.\d+)? seconds", r"\1<duration> seconds", text)
    text = re.sub(r"(?m)^(random seed:|hash randomization:).*$", r"\1 <seed>", text)
    return re.sub(r"(?<= at )0x[0-9a-fA-F]+", "<address>", text)


def excerpt(text: str, limit=2200) -> str:
    # Normalize BEFORE slicing, otherwise changing the length of a duration can
    # shift the first byte of the excerpt and create an artificial cache miss.
    return stable_log(text)[-limit:]
