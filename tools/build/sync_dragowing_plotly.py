"""Sync the Plotly runtime inside the standalone pysaiyanweboo.py distribution."""
import argparse
import hashlib
import subprocess
from pathlib import Path

UPSTREAM = "35c16e6fa2482372582460e38faf7f376b01d145"
SHA256 = "1f51bb5c7bf989c23596ac80492f7be6c5d3e22d5e017839debbd6764577dbc2"
TARGET = Path(__file__).resolve().parents[2] / "pysaiyanweboo.py"
BEGIN = b"# BEGIN DRAgoWing Plotly runtime\n"
END = b"# END DRAgoWing Plotly runtime\n"


def bounds(source):
    if source.count(BEGIN) != 1 or source.count(END) != 1:
        raise ValueError("expected one DRAgoWing runtime")
    start = source.index(BEGIN)
    return start, source.index(END, start) + len(END)


def verify(block):
    if hashlib.sha256(block).hexdigest() != SHA256:
        raise ValueError("DRAgoWing Plotly runtime differs from the pinned source")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-repo", type=Path, help="copy from the pinned commit in a DRAgoWing checkout")
    args = parser.parse_args()
    source = TARGET.read_bytes()
    start, end = bounds(source)
    if args.from_repo is None:
        verify(source[start:end])
        return
    upstream = subprocess.check_output(["git", "-C", str(args.from_repo), "show", UPSTREAM + ":dragowing.py"])
    first, last = bounds(upstream)
    block = upstream[first:last]
    verify(block)
    TARGET.write_bytes(source[:start] + block + source[end:])


if __name__ == "__main__":
    main()
