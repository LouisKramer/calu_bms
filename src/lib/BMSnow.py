import espnow
import micropython
from common.logger import *

class BMSnow:
    SEARCH_MSG   = 10
    HELLO_MSG    = 20
    WELCOME_MSG  = 30
    DATA_MSG     = 40
    DATA_REQ_MSG = 50
    CONF_MSG     = 60
    CONF_ACK_MSG = 70
    SYNC_REQ_MSG = 80 # Request from master to slave
    SYNC_ACK_MSG = 90  # Ack from slave to master
    SYNC_REF_MSG = 100 # Reference from master to slave
    SYNC_FIN_MSG = 110 # Final ack from slave to master
    def __init__(self, espnow: espnow.ESPnow = None):
        self.e = espnow
        self.log = create_logger("BMSnow", level=LogLevel.INFO)
        self.wifi_channel = 1
    def listener(self):
        while True:
            mac, msg = self.e.irecv(0)  # non-blocking
            if mac is None or not msg:
                return
            msg_type = msg[0]
            if msg_type == BMSnow.SEARCH_MSG:
                micropython.schedule(self._handle_search_msg,mac,msg)
            if msg_type == BMSnow.HELLO_MSG:
                micropython.schedule(self._handle_hello_msg, mac, msg)
            if msg_type == BMSnow.WELCOME_MSG:
                micropython.schedule(self._handle_welcome_msg, mac, msg)
            if msg_type == BMSnow.DATA_MSG:
                micropython.schedule(self._handle_data_ms, mac, msg)
            if msg_type == BMSnow.DATA_REQ_MSG:
                micropython.schedule(self._handle_data_req_msg, mac, msg)
            if msg_type == BMSnow.CONF_MSG:
                micropython.schedule(self._handle_conf_msg, mac, msg)
            if msg_type == BMSnow.CONF_ACK_MSG:
                micropython.schedule(self._handle_conf_ack_msg, mac, msg)
            if msg_type == BMSnow.SYNC_REQ_MSG:
                micropython.schedule(self._handle_sync_req_msg, mac, msg)
            if msg_type == BMSnow.SYNC_ACK_MSG:
               micropython.schedule( self._handle_sync_ack_msg, mac, msg)
            else:
                pass
    def _handle_search_msg(self, mac, msg):
        pass


class master(BMSnow):
    def __init__(self):

        pass
    def discover(self):
        pass
    def data(self):
        pass
    def sync(self):
        pass



class slave(BMSnow):
    def __init__(self, espnow: espnow.ESPnow = None):
        super().__init__(self, espnow)
        pass
    def _handle_search_msg(self, mac, msg):
        self.log.info(f"Received SEARCH from {self.log.mac_to_str(mac)}", ctx="slave_search_handler")