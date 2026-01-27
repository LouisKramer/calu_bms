# Makefile for ESP32 MicroPython project deployment

# Path to fw binary
FW_BINARY := bin/ESP32_GENERIC_S3-SPIRAM_OCT-20251209-v1.27.0.bin
# Path to your requirements.txt (adjust if needed)
REQUIREMENTS_MASTER := src/master/requirements.txt
REQUIREMENTS_SLAVE := src/slave/requirements.txt
# Optional: specify your serial port here, or pass via command line: make PORT=/dev/ttyUSB0
PORT ?=

# Python command (use python3 if needed)
PYTHON := python

# Default target: clean + upload
.PHONY: all_slave
all_slave: clean appl_slave soft_reset

.PHONY: all_master
all_master: clean appl_master soft_reset

# Program firmware (upload only)
.PHONY: fw
fw:
	@echo "=== Programming firmware ==="
#mpremote $(if $(PORT),connect $(PORT)) bootloader
	mpremote bootloader
	Start-Sleep -Seconds 5
	mpremote reset
	Start-Sleep -Seconds 5
	esptool erase-flash
	Start-Sleep -Seconds 5
	esptool --baud 460800 write-flash 0 $(FW_BINARY)
	@echo "Firmware programming complete!"

# Hard reset
.PHONY: reset
reset:
	@echo "=== PERFORMING RESET ==="
	mpremote $(if $(PORT),connect $(PORT)) reset
	@echo "Reset done."

# Soft reset the MicroPython interpreter (equivalent to Ctrl+D)
.PHONY: soft_reset
soft_reset:
	@echo "=== PERFORMING SOFT RESET (Ctrl+D) ==="
	mpremote $(if $(PORT),connect $(PORT)) soft-reset
	@echo "Soft reset done."

# Delete everything on the device
.PHONY: clean
clean:
	@echo "=== RESETTING ESP32 FILESYSTEM ==="
	mpremote fs rm -r ./
	@echo ""

# Upload all files from requirements.txt
.PHONY: appl_master
appl_master:
	@echo "=== UPLOADING MASTER FILES ==="
	mpremote mip install ./src/master/package.json
	@echo "Deployment complete!"

# Upload slave files
.PHONY: appl_slave
appl_slave:
	@echo "=== UPLOADING SLAVE FILES ==="
	mpremote mip install ./src/slave/package.json
	@echo "Slave deployment complete!"

# Connect to REPL (interactive console)
.PHONY: repl
repl:
	mpremote $(if $(PORT),connect $(PORT)) repl

# List files on device
.PHONY: ls
ls:
	mpremote $(if $(PORT),connect $(PORT)) fs ls :

# Run main.py on device after upload
.PHONY: run
run:
	mpremote $(if $(PORT),connect $(PORT)) run :main.py

# Help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make                # Clean + upload (full fresh deploy)"
	@echo "  make all_master     # Same as above for master"
	@echo "  make all_slave      # Same as above for slave"
	@echo "  make fw             # Program firmware"
	@echo "  make reset          # Hard reset"
	@echo "  make soft_reset     # Restart MicroPython interpreter (Ctrl+D)"
	@echo "  make clean          # Delete all files on device"
	@echo "  make appl_master    # Upload master files without cleaning"
	@echo "  make appl_slave     # Upload slave files without cleaning"
	@echo "  make repl           # Open interactive REPL"
	@echo "  make ls             # List files on device"
	@echo "  make run            # Execute main.py"
	@echo ""
	@echo "Optional: PORT=/dev/ttyUSB0 make <target>   (or COM3 on Windows)"