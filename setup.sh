#!/usr/bin/env bash
# One-time setup: a Python environment in .venv with both Unitree SDKs (cable and Wi-Fi).
# Takes under a minute and needs internet. Run it again after moving or renaming this folder.
#   bash setup.sh                                  uses python3.10 from your PATH
#   PYTHON=/path/to/python3.10 bash setup.sh       uses that Python (for example a conda environment)
# Python 3.10 is required: the cable SDK needs cyclonedds 0.10.2, which has ready-made packages only up to 3.10.
# Nothing outside this folder is changed.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-$(command -v python3.10 || true)}"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 10))' 2>/dev/null; then
  echo "Python 3.10 is needed (found: ${PY:-none})."
  echo "Install it with the macOS installer from https://www.python.org/downloads/release/python-31011/"
  echo "(\"macOS 64-bit universal2 installer\"), then run  bash setup.sh  again."
  echo "Your other Python versions can stay: 3.10 installs next to them."
  echo "With conda instead:  conda create -y -n go2 python=3.10"
  echo "                     PYTHON=\"\$(conda info --base)/envs/go2/bin/python\" bash setup.sh"
  exit 1
fi
if ! "$PY" -c "import tkinter" 2>/dev/null; then
  echo "This Python has no tkinter, which the panel's window needs. The python.org installer includes it."
  exit 1
fi
echo "using $PY"
"$PY" -m venv --clear .venv   # --clear: a fresh environment, also after the folder was moved
.venv/bin/pip install -q --upgrade pip
echo "installing the cable SDK (unitree_sdk2py + cyclonedds)..."
.venv/bin/pip install -q cyclonedds==0.10.2 numpy
.venv/bin/pip install -q --no-deps \
  "https://github.com/unitreerobotics/unitree_sdk2_python/archive/814556d15970dd2ecf1c9984e845ca02ab07e206.zip"
echo "installing the Wi-Fi library (unitree_webrtc_connect)..."
# without pyaudio (needs a C build and is only used for audio) and opencv (photos are saved with pillow)
.venv/bin/pip install -q "aiortc>=1.9.0" pycryptodome requests curl_cffi wasmtime lz4 packaging sounddevice pydub pillow
.venv/bin/pip install -q --no-deps unitree_webrtc_connect==2.2.0
.venv/bin/python -c "
from unitree_sdk2py.go2.sport.sport_client import SportClient
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection
print('Setup done. Start the panel with:  .venv/bin/python control_panel.py   (or double-click start.command)')"
