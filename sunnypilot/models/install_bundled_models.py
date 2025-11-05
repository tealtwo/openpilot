# Install bundled custom models to device storage.

import os
import shutil
import hashlib
from pathlib import Path
from openpilot.system.hardware.hw import Paths
from openpilot.common.basedir import BASEDIR

BUNDLED_MODELS_DIR = Path(BASEDIR) / "sunnypilot" / "models" / "custom"
DEVICE_MODELS_DIR = Path(Paths.model_root())


def calculate_sha256(file_path: Path) -> str:
  """Calculate SHA256 hash of a file"""
  sha256_hash = hashlib.sha256()
  with open(file_path, "rb") as f:
    for chunk in iter(lambda: f.read(4096), b""):
      sha256_hash.update(chunk)
  return sha256_hash.hexdigest()


def install_bundled_models():
  """
  Copy bundled custom models to device storage if not already present or if hash mismatches.
  """
  if not BUNDLED_MODELS_DIR.exists():
    print(f"[install_bundled_models] No bundled models directory found at {BUNDLED_MODELS_DIR}")
    return

  # Create device models directory if it doesn't exist
  DEVICE_MODELS_DIR.mkdir(parents=True, exist_ok=True)

  # Get all files from bundled models directory
  bundled_files = list(BUNDLED_MODELS_DIR.glob("*"))

  if not bundled_files:
    print(f"[install_bundled_models] No bundled model files found")
    return

  print(f"[install_bundled_models] Found {len(bundled_files)} bundled model files")

  for bundled_file in bundled_files:
    if bundled_file.is_file():
      device_file = DEVICE_MODELS_DIR / bundled_file.name

      should_copy = False

      if not device_file.exists():
        print(f"[install_bundled_models] Installing {bundled_file.name} (not found on device)")
        should_copy = True
      else:
        # Check if hashes match
        bundled_hash = calculate_sha256(bundled_file)
        device_hash = calculate_sha256(device_file)

        if bundled_hash != device_hash:
          print(f"[install_bundled_models] Updating {bundled_file.name} (hash mismatch)")
          should_copy = True
        else:
          print(f"[install_bundled_models] {bundled_file.name} already up to date")

      if should_copy:
        try:
          shutil.copy2(bundled_file, device_file)
          print(f"[install_bundled_models] ✓ Copied {bundled_file.name}")
        except Exception as e:
          print(f"[install_bundled_models] ✗ Failed to copy {bundled_file.name}: {e}")

  print(f"[install_bundled_models] Installation complete")


if __name__ == "__main__":
  install_bundled_models()
