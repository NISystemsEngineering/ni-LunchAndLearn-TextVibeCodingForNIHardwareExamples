"""Launches RTG Server and prints its output to diagnose startup failures."""
import subprocess
from pathlib import Path

RTG_SERVER_EXE = Path(r"C:\Program Files\National Instruments\RTG\app\RTG Server.exe")

print(f"Launching: {RTG_SERVER_EXE}\n")

result = subprocess.run(
    [str(RTG_SERVER_EXE)],
    capture_output=True,
    text=True,
    timeout=60,
)

print(f"Exit code: {result.returncode}")
if result.stdout:
    print("STDOUT:\n", result.stdout)
if result.stderr:
    print("STDERR:\n", result.stderr)
if not result.stdout and not result.stderr:
    print("(no output captured)")
