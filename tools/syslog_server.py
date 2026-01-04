import socketserver
import logging
import datetime

# Configuration
HOST = "0.0.0.0"          # Listen on all interfaces
PORT = 514               # Change to 514 if running as Administrator
LOG_FILE = "syslog_messages.log"  # Log file name

# Set up logging to file (append mode)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename=LOG_FILE,
    filemode="a"
)

class SyslogUDPHandler(socketserver.BaseRequestHandler):
    """
    Handler for incoming syslog messages.
    """
    def handle(self):
        # Get the raw data and client address
        data = self.request[0].strip()
        client_ip = self.client_address[0]
        
        # Decode and prepare the message
        try:
            message = data.decode("utf-8", errors="replace")
        except:
            message = str(data)
        
        # Print to console
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{client_ip}] {message}")
        
        # Log to file
        logging.info(f"[{client_ip}] {message}")

if __name__ == "__main__":
    print(f"Starting syslog server on {HOST}:{PORT}...")
    print(f"Logs will be saved to {LOG_FILE}")
    print("Press Ctrl+C to stop.\n")
    
    try:
        server = socketserver.UDPServer((HOST, PORT), SyslogUDPHandler)
        server.serve_forever()  # Run indefinitely
    except PermissionError:
        print(f"Error: Cannot bind to port {PORT}. Try a higher port (e.g., 5140) or run as Administrator.")
    except KeyboardInterrupt:
        print("\nServer stopped.")