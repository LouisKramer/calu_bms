"""Compile every MicroPython source under src/ with mpy-cross to catch syntax errors before upload."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "src"


def main():
    failed = 0
    files = sorted(ROOT.rglob("*.py"))
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "out.mpy")
        for f in files:
            r = subprocess.run([sys.executable, "-m", "mpy_cross", "-o", out, str(f)],
                               capture_output=True, text=True)
            if r.returncode:
                failed += 1
                print(f"FAIL {f.relative_to(ROOT)}\n{r.stderr.strip()}")
    print(f"{len(files) - failed}/{len(files)} files compile")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
