"""
Upload files listed in a requirements.txt-like mapping to a MicroPython device
using a single mpremote session.

Each non-comment line: <local path relative to the requirements file> <device path>
Local paths may contain glob patterns; then the device path must end with '/'
(directory) or contain '*' (replaced by the file name).
"""
import argparse
import glob
import subprocess
import sys
from pathlib import Path

CLEAN_CODE = """
import os
KEEP = {keep!r}
def _rm(p):
    if os.stat(p)[0] & 0x4000:
        for n in os.listdir(p):
            _rm(p + '/' + n)
        os.rmdir(p)
    else:
        os.remove(p)
for n in os.listdir('/'):
    if n not in KEEP:
        _rm('/' + n)
print('device cleaned, kept:', [n for n in os.listdir('/')])
"""

MKDIR_CODE = """
import os
for d in {dirs!r}:
    try:
        os.mkdir(d)
    except OSError:
        pass
"""


def parse_requirements(req_file: Path):
    base_dir = req_file.parent
    pairs = []
    with open(req_file, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) != 2:
                sys.exit(f"{req_file}:{lineno}: expected '<local> <dest>', got: {line}")
            raw_local, raw_dest = parts
            dest = raw_dest[2:] if raw_dest.startswith("./") else raw_dest.lstrip("/")
            pattern = str(base_dir / raw_local)
            if glob.has_magic(raw_local):
                matches = sorted(Path(p) for p in glob.glob(pattern) if Path(p).is_file())
                if not matches:
                    print(f"Warning: no files matched '{raw_local}'")
                for m in matches:
                    if "*" in dest:
                        pairs.append((m.resolve(), dest.replace("*", m.name)))
                    else:
                        pairs.append((m.resolve(), dest.rstrip("/") + "/" + m.name))
            else:
                local = Path(pattern).resolve()
                if not local.is_file():
                    print(f"Warning: '{raw_local}' not found, skipped")
                    continue
                pairs.append((local, dest))
    return pairs


def remote_dirs(pairs):
    dirs = set()
    for _, dest in pairs:
        parts = dest.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            dirs.add("/" + "/".join(parts[:i]))
    return sorted(dirs, key=lambda d: d.count("/"))


def build_command(pairs, port=None, clean=False, keep=("data",)):
    cmd = [sys.executable, "-m", "mpremote"]
    if port:
        cmd += ["connect", port]
    chain = []
    if clean:
        chain.append(["exec", CLEAN_CODE.format(keep=list(keep))])
    dirs = remote_dirs(pairs)
    if dirs:
        chain.append(["exec", MKDIR_CODE.format(dirs=dirs)])
    for local, dest in pairs:
        chain.append(["cp", str(local), ":" + dest])
    for i, part in enumerate(chain):
        if i:
            cmd.append("+")
        cmd += part
    return cmd


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("requirements_file", type=Path, nargs="?",
                        help="File mapping; omit together with --clean to only wipe the device")
    parser.add_argument("--port", help="Serial port (e.g. COM5 or /dev/ttyACM0); auto-detect if omitted")
    parser.add_argument("--clean", action="store_true", help="Delete everything on the device first (except --keep)")
    parser.add_argument("--keep", nargs="*", default=["data"], help="Top-level device entries kept by --clean")
    parser.add_argument("--dry-run", action="store_true", help="Print the mpremote command without running it")
    args = parser.parse_args()

    if args.requirements_file is None:
        if not args.clean:
            parser.error("requirements_file is required unless --clean is given")
        pairs = []
    elif not args.requirements_file.is_file():
        sys.exit(f"Error: {args.requirements_file} not found.")
    else:
        pairs = parse_requirements(args.requirements_file)
    for local, dest in pairs:
        print(f"  {local} -> :{dest}")
    cmd = build_command(pairs, args.port, args.clean, args.keep)
    if args.dry_run:
        print(" ".join(f'"{c}"' if (" " in c or "\n" in c) else c for c in cmd))
        return
    print(f"Running mpremote ({len(pairs)} file(s){', clean first' if args.clean else ''})...")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"mpremote failed with exit code {result.returncode}")
    print("Done!")


if __name__ == "__main__":
    main()
