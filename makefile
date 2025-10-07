# Makefile to deploy files and reset a device using ampy on Windows

# Default target
.PHONY: deploy reset

deploy:
	@echo Deploying files using deploy.py...
	python deploy.py
	@echo Resetting device on COM4...
	$(MAKE)reset
	@echo Deployment and reset complete.

reset:
	@echo Resetting device on COM4...
	@ampy --port COM4 put reset.py
	@ampy --port COM4 run reset.py
	@echo Reset complete.