"""Run this script once to generate the gRPC Python stubs from the RTG proto file."""
import subprocess
import sys
from pathlib import Path

PROTO_PATH = Path(
    r"C:\Program Files\National Instruments\LabVIEW 2023\vi.lib\RTG\api\remote"
)
PROTO_FILE = "rtg_api_service.proto"
OUT_DIR = Path(__file__).parent / "generated"

OUT_DIR.mkdir(exist_ok=True)

result = subprocess.run(
    [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={PROTO_PATH}",
        f"--python_out={OUT_DIR}",
        f"--grpc_python_out={OUT_DIR}",
        str(PROTO_PATH / PROTO_FILE),
    ],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print("STDERR:", result.stderr)
    sys.exit(result.returncode)

# Create __init__.py so the package is importable
(OUT_DIR / "__init__.py").touch()
print(f"Stubs generated in: {OUT_DIR}")
