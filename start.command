#!/bin/bash
# Double-click to open the Go2 Control Panel. Run  bash setup.sh  once first.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "The panel is not installed yet: open Terminal in this folder and run  bash setup.sh"
  read -r -p "Press Enter to close."
  exit 1
fi
exec .venv/bin/python control_panel.py
