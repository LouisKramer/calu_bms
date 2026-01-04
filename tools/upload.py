import argparse
import os
import subprocess
import sys
from pathlib import Path

def run_mpremote(cmd_args):
    """Run mpremote command and handle non-fatal errors gracefully."""
    full_cmd = ["mpremote"] + cmd_args
    print(f"Running: {' '.join(full_cmd)}")
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        # Ignore "file exists" errors for mkdir (directory already there)
        if "EEXIST" in err or "File exists" in err:
            print("  (directory already exists, continuing)")
            return
        print(f"Error: {err}")
        sys.exit(1)
    else:
        if result.stdout.strip():
            print(result.stdout.strip())

def create_remote_dir(remote_dir: str):
    """Create remote directories level by level, skipping root."""
    # Normalize and skip if empty or just root
    remote_dir = remote_dir.rstrip("/").lstrip("/")
    if not remote_dir:
        return

    parts = remote_dir.split("/")
    current = ""

    for part in parts:
        if part:
            current += "/" + part
            print(f"Ensuring remote directory: {current}")
            run_mpremote(["mkdir", f":{current}"])

def upload_file(local_path: Path, remote_path: str):
    """Upload a single file, creating necessary remote directories."""
    # Normalize remote path: remove leading ./ and ensure no double slashes
    remote_path = remote_path.lstrip("./")
    if remote_path.startswith("/"):
        remote_path = remote_path[1:]

    remote_dir = os.path.dirname(remote_path)
    if remote_dir:
        create_remote_dir(remote_dir)
    
    print(f"Uploading to: /{remote_path}")
    run_mpremote(["cp", str(local_path), f":{remote_path}"])

def main(req_file: Path, port: str | None = None):
    if not req_file.exists():
        print(f"Error: {req_file} not found.")
        sys.exit(1)

    base_dir = req_file.parent
    print(f"Parsing {req_file} (base directory: {base_dir})")

    with open(req_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    print(f"Found {len(lines)} entries to upload.\n")

    connect_args = ["connect", port] if port else []

    for line in lines:
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            print(f"Skipping invalid line: {line}")
            continue

        raw_local, raw_dest = parts
        # Resolve local path relative to requirements.txt location
        local_pattern = (base_dir / raw_local.replace("/", os.sep)).resolve()

        # Find matching files (handles globs like *.py)
        matching_locals = list(Path(base_dir).rglob(raw_local.lstrip("/\\")))
        if not matching_locals:
            print(f"Warning: No files matched pattern '{raw_local}'")
            continue

        for local_path in matching_locals:
            if not local_path.is_file():
                print(f"Skipping non-file: {local_path}")
                continue

            # Compute destination path
            if "*" in raw_dest:
                dest_path = raw_dest.replace("*", local_path.name)
            else:
                dest_path = raw_dest

            # Clean destination path
            dest_path = dest_path.lstrip("./")

            print(f"Uploading {local_path} → /{dest_path}")

            # Upload (with or without explicit port)
            if port:
                run_mpremote(connect_args + ["cp", str(local_path), f":{dest_path}"])
            else:
                upload_file(local_path, dest_path)

    print("\nUpload complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Upload files to ESP32 MicroPython based on a requirements.txt-like file."
    )
    parser.add_argument(
        "requirements_file",
        nargs="?",
        default="requirements.txt",
        help="Path to the requirements file",
    )
    parser.add_argument(
        "--port",
        help="Serial port (e.g. COM3 or /dev/ttyUSB0)",
    )
    args = parser.parse_args()

    main(Path(args.requirements_file), args.port)