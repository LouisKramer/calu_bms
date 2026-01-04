# Makefile for ESP32 MicroPython project deployment

# Path to fw binary
FW_BINARY := bin/ESP32_GENERIC_S3-SPIRAM_OCT-20250911-v1.26.1.bin

# Path to your requirements.txt (adjust if needed)
REQUIREMENTS := src/master/requirements.txt

# Optional: specify your serial port here, or pass via command line: make PORT=/dev/ttyUSB0
PORT ?=

# Python command (use python3 if needed)
PYTHON := python

# Scripts (place these in the same directory as the Makefile)
UPLOAD_SCRIPT := tools/upload.py

# Default target: clean + upload
.PHONY: all
all: clean upload soft_reset

# Program firmware (upload only)
.PHONY: fw
fw:
	@echo "=== Programming firmware ==="
	mpremote $(if $(PORT),connect $(PORT)) soft-reset
	mpremote $(if $(PORT),connect $(PORT)) bootloader
	esptool erase-flash
	esptool --baud 460800 write_flash 0 $(FW_BINARY)
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
.PHONY: upload
upload:
	@echo "=== UPLOADING PROJECT FILES ==="
	$(PYTHON) $(UPLOAD_SCRIPT) $(REQUIREMENTS) $(if $(PORT),--port $(PORT))
	@echo "Deployment complete!"

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
	@echo "  make fw             # Program firmware"
	@echo "  make all            # Same as above"
	@echo "  make reset          # Hard reset"
	@echo "  make soft_reset     # Restart MicroPython interpreter (Ctrl+D)"
	@echo "  make clean          # Delete all files on device"
	@echo "  make upload         # Upload files without cleaning"
	@echo "  make repl           # Open interactive REPL"
	@echo "  make ls             # List files on device"
	@echo "  make run            # Execute main.py"
	@echo ""
	@echo "Optional: PORT=/dev/ttyUSB0 make <target>   (or COM3 on Windows)"