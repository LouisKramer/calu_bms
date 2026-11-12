# Makefile for CALU BMS (ESP32-S3, MicroPython) deployment
#
# Usage: make <target> [PORT=COM5]
#   PORT     serial port of the running MicroPython device (auto-detect if empty)
#   ESPPORT  serial port for esptool (auto-detect if empty; the ROM bootloader
#            may enumerate on a different port than MicroPython)

PYTHON   ?= python
PORT     ?=
ESPPORT  ?=

FW_BINARY := bin/ESP32_GENERIC_S3-SPIRAM_OCT-20250911-v1.26.1.bin
REQUIREMENTS_SLAVE  := src/slave/requirements.txt
UPLOAD := $(PYTHON) tools/upload.py $(if $(PORT),--port $(PORT))

MPREMOTE := $(PYTHON) -m mpremote $(if $(PORT),connect $(PORT))
ESPTOOL  := $(PYTHON) -m esptool --chip esp32s3 $(if $(ESPPORT),--port $(ESPPORT))

# KiCad 10 (hardware design in hw/slave_3_0, run with KiCad's own Python)
KICAD_DIR ?= C:/Program Files/KiCad/10.0
KICAD_PY  := "$(KICAD_DIR)/bin/python.exe"
KICAD_CLI := "$(KICAD_DIR)/bin/kicad-cli.exe"
HW_DIR    := hw/slave_3_0
HW_OUT    := $(HW_DIR)/kicad

.DEFAULT_GOAL := help

# Full fresh deploy: wipe device (keeps /data with calibration), upload, restart app
.PHONY: all_slave
all_slave: check
	@echo === DEPLOYING SLAVE ===
	$(UPLOAD) $(REQUIREMENTS_SLAVE) --clean
	$(MPREMOTE) reset

# Upload without wiping the device
.PHONY: appl_slave
appl_slave:
	$(UPLOAD) $(REQUIREMENTS_SLAVE)

# Program MicroPython firmware (erases the whole flash, including /data)
.PHONY: fw
fw:
	@echo === PROGRAMMING FIRMWARE ===
	-$(MPREMOTE) bootloader
	$(PYTHON) -c "import time; time.sleep(3)"
	$(ESPTOOL) --baud 460800 write-flash --erase-all 0 $(FW_BINARY)
	@echo Firmware programming complete!

# Hard reset (runs boot.py and main.py)
.PHONY: reset
reset:
	$(MPREMOTE) reset

# Restart interpreter into raw REPL (does NOT run main.py)
.PHONY: soft_reset
soft_reset:
	$(MPREMOTE) soft-reset

# Delete everything on the device except /data
.PHONY: clean
clean:
	$(UPLOAD) --clean

.PHONY: repl
repl:
	$(MPREMOTE) repl

.PHONY: ls
ls:
	$(MPREMOTE) tree :

# Slave hardware bring-up checks (runs local script; libraries come from appl_slave/all_slave)
.PHONY: bringup
bringup:
	$(MPREMOTE) run src/slave/bringup.py

# MicroPython syntax check of all sources (no device needed)
.PHONY: check
check:
	$(PYTHON) tools/check.py

# ---------------------------------------------------------------- hardware (KiCad 10 + SKiDL)
# Netlist + verified schematic from the SKiDL source (hw/slave_3_0/*.py)
.PHONY: sch
sch:
	$(KICAD_PY) $(HW_DIR)/slave_3_0.py

# Same, plus the initial PCB if it does not exist yet (never overwrites a layout)
.PHONY: pcb
pcb:
	$(KICAD_PY) $(HW_DIR)/slave_3_0.py --pcb

.PHONY: erc
erc:
	$(KICAD_CLI) sch erc --severity-all --exit-code-violations -o $(HW_OUT)/erc.rpt $(HW_OUT)/slave_3_0.kicad_sch

.PHONY: drc
drc:
	$(KICAD_CLI) pcb drc --schematic-parity --severity-error -o $(HW_OUT)/drc.rpt $(HW_OUT)/slave_3_0.kicad_pcb

# Install SKiDL into KiCad's Python
.PHONY: hw_tools
hw_tools:
	$(KICAD_PY) -m pip install --user skidl

# Install host tools
.PHONY: tools
tools:
	$(PYTHON) -m pip install --user mpremote esptool mpy-cross==1.26.*

.PHONY: help
help:
	@echo Available targets:
	@echo   make all_slave      check, wipe device (keeps /data), upload slave, reset
	@echo   make appl_slave     upload slave files without wiping
	@echo   make fw             flash MicroPython firmware (erases everything)
	@echo   make reset          hard reset (starts main.py if present)
	@echo   make soft_reset     restart interpreter into raw REPL (main.py not run)
	@echo   make clean          delete all files on device except /data
	@echo   make repl           interactive REPL
	@echo   make ls             list files on device
	@echo   make bringup        slave hardware bring-up checks
	@echo   make check          MicroPython syntax check of src/
	@echo   make tools          pip install mpremote, esptool, mpy-cross
	@echo   make sch            hardware: netlist + verified KiCad schematic from SKiDL
	@echo   make pcb            hardware: same + initial PCB (only if none exists)
	@echo   make erc / drc      hardware: KiCad ERC / DRC (incl. schematic parity)
	@echo   make hw_tools       install SKiDL into KiCad's Python
	@echo Options: PORT=COM5 (device), ESPPORT=COM6 (esptool), PYTHON=python3, KICAD_DIR=...
