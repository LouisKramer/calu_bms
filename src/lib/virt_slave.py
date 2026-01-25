from common.common import *
from common.logger import *

log_slave=Logger()
# ----------------------------------------------------------------------
#  Slaves – dynamic container with a hard upper limit (MAX_NR_OF_SLAVES)
# ----------------------------------------------------------------------
class Slaves:
    MAX_NR_OF_SLAVES = 16    
    def __init__(self):
        log_slave.info("Initializing slave handler...")

        self.T1 = 0
        # start with an *empty* list – we grow only when push() is called
        self._slaves: list["virt_slave | None"] = []

    # ------------------------------------------------------------------
    #  Basic bookkeeping
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        """Number of active (non-None) slaves."""
        return sum(1 for s in self._slaves if s is not None)

    def __iter__(self):
        """Iterate over active slaves only."""
        return (s for s in self._slaves if s is not None)

    def nr_of_slaves(self) -> int:
        return len(self._slaves)

    # ------------------------------------------------------------------
    #  Core CRUD operations 
    # ------------------------------------------------------------------
    def push(self, info: info_data):
        """Add a new slave if there is room"""
        if len(self._slaves) >= self.MAX_NR_OF_SLAVES:
            log_slave.warn(f"Cannot add more than {self.MAX_NR_OF_SLAVES} slaves")
            return None
        else:
            log_slave.info(f"Add slave {log_slave.mac_to_str(info.mac)} to list")
            new = virt_slave(info)
            for i, s in enumerate(self._slaves):
                if s is None:
                    self._slaves[i] = new
                    return new
            self._slaves.append(new)
            return new

    def pop(self, info: info_data) -> bool:
        """Remove slave identified by MAC address."""
        for i, s in enumerate(self._slaves):
            if s is not None and s.battery.info.mac == info.mac:
                log_slave.info(f"Remove slave {log_slave.mac_to_str(info.mac)} from list")
                del self._slaves[i]        # keep a hole – list stays compact
                return True
        log_slave.warn(f"Unable to remove slave {log_slave.mac_to_str(info.mac)} from list")
        return False

    def get_by_mac(self, mac):
        for s in self._slaves:
            if s is not None and s.battery.info.mac == mac:
                return s
        return None

    def get_by_addr(self, addr):
        for s in self._slaves:
            if s is not None and s.battery.info.addr == addr:
                return s
        return None

    def is_known(self, mac) -> bool:
        return any(s is not None and s.battery.info.mac == mac for s in self._slaves)
    
class virt_slave(Slaves):
    def __init__(self, info: info_data):
        self.battery = battery()
        self.battery.info.set(info)
        self.battery.create_measurements()
    
