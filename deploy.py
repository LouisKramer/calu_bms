import os
import subprocess
from pathlib import Path

# Configuration
SRC_DIR = "./src/slave"
PORT = "COM4"

def get_all_files(directory):
    """Recursively get all files in the specified directory."""
    directory_path = Path(directory)
    return [str(file) for file in directory_path.rglob("*") if file.is_file()]

def deploy_files():
    """Deploy all files in SRC_DIR to the device using ampy."""
    print("Deploying files to device on", PORT, "...")
    
    # Get all files
    files = get_all_files(SRC_DIR)
    
    if not files:
        print("No files found in", SRC_DIR)
        return
    
    # Transfer each file using ampy
    for file in files:
        print(f"Transferring {file}")
        try:
            # Run ampy command to transfer the file, preserving the path
            subprocess.run(
                ["ampy", "--port", PORT, "put", file, file],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error transferring {file}: {e.stderr}")
        except FileNotFoundError:
            print("Error: ampy not found. Ensure ampy is installed and in PATH.")
            return
    
    print("Deployment complete.")

if __name__ == "__main__":
    deploy_files()