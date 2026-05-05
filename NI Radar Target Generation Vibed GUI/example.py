"""Example: initialize RTG, run a range/velocity scenario, then shut down."""
import subprocess
import time
import sys
from pathlib import Path
from client import RtgClient, SyncMode

INSTRUMENT = "5841_8"   # NI MAX resource name
SERVER = "localhost:50052"
DEVICE = 0
RTG_SERVER_EXE = Path(r"C:\Program Files\National Instruments\RTG\app\RTG Server.exe")
SERVER_STARTUP_TIMEOUT = 30  # seconds to wait for server to become ready


def start_rtg_server() -> subprocess.Popen:
    if not RTG_SERVER_EXE.exists():
        print(f"ERROR: RTG Server not found at {RTG_SERVER_EXE}")
        sys.exit(1)
    print("Starting RTG Server...")
    proc = subprocess.Popen([str(RTG_SERVER_EXE)])
    # Wait for server to start accepting connections
    import grpc
    deadline = time.time() + SERVER_STARTUP_TIMEOUT
    while time.time() < deadline:
        # Detect if the server process exited early
        if proc.poll() is not None:
            print(f"ERROR: RTG Server exited unexpectedly (exit code {proc.returncode}).")
            sys.exit(1)
        try:
            channel = grpc.insecure_channel(SERVER)
            grpc.channel_ready_future(channel).result(timeout=1)
            channel.close()
            print("RTG Server is ready.")
            return proc
        except grpc.FutureTimeoutError:
            pass
    print("ERROR: RTG Server did not become ready within 30 seconds.")
    proc.terminate()
    sys.exit(1)


server_proc = start_rtg_server()

with RtgClient(SERVER) as rtg:
    # --- discovery ---
    resources = rtg.query_system_resources()
    print("Found devices:", resources["resource_names"])

    # --- configure (must be done before start) ---
    status = rtg.get_status()
    print(f"RTG state: {status['state']}")
    if status["state"].lower() == "idle":
        print("Initializing RTG...")
        rtg.initialize([INSTRUMENT])
        print("Initialized.")
    elif status["state"].lower() == "active":
        print("RTG is active, stopping first...")
        rtg.stop()
        print("Stopped.")

    print(f"Version: {rtg.get_version(DEVICE)}")

    print(f"Setting center frequency to 5.5 GHz...")
    rtg.set_center_frequency(DEVICE, 5.5e9)
    print(f"Setting reference level to -10 dBm...")
    rtg.set_reference_level(DEVICE, -10.0)
    print(f"Setting common attenuation to 20 dB...")
    coerced = rtg.set_common_attenuation(DEVICE, 20.0)
    print(f"  Coerced attenuation: {coerced} dB")
    print(f"Enabling frequency correction...")
    rtg.enable_frequency_correction(DEVICE, True)

    # --- run ---
    print("\nStarting RTG...")
    rtg.start()
    print(f"Status: {rtg.get_status()}")

    # Send two targets: 50 m / 10 m/s and 120 m / -5 m/s
    print("\nSending target configuration (range/velocity)...")
    rtg.send_targets_range_velocity(
        DEVICE,
        targets=[
            {"range": 50.0,  "velocity": 10.0, "attenuation": 20.0, "enable": True},
            {"range": 120.0, "velocity": -5.0, "attenuation": 30.0, "enable": True},
        ],
        sync_mode=SyncMode.SOFTWARE_TRIGGER,
    )
    print("  Target 1: range=50 m, velocity=10 m/s, attenuation=20 dB")
    print("  Target 2: range=120 m, velocity=-5 m/s, attenuation=30 dB")

    print("Sending software trigger...")
    rtg.send_software_trigger(DEVICE)
    print("Trigger sent.")

    # Monitor signal
    max_pwr = rtg.read_max_power(DEVICE)
    print(f"\nMax output power (mag²): {max_pwr:.4f}")
    overflow = rtg.read_overflow_status(DEVICE)
    print(f"Overflow: {overflow}")

    # --- clean up ---
    print("\nStopping RTG...")
    rtg.stop()
    print("Closing RTG...")
    rtg.close()
    print("Done.")
