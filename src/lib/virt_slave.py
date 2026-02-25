from common.common import *
from common.logger import *


# ----------------------------------------------------------------------
#  Slaves – dynamic container with a hard upper limit (MAX_NR_OF_SLAVES)
# ----------------------------------------------------------------------
class Slaves:
    MAX_NR_OF_SLAVES = 16    
    def __init__(self):
        self.log=Logger()
        self.slave_lost_flag = False
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
    
    def nr_of_cells(self) -> int:
        return sum(s.battery.info.ncell for s in self._slaves if s is not None)

    # ------------------------------------------------------------------
    #  Core CRUD operations 
    # ------------------------------------------------------------------
    def push(self, mac, addr, ncell, ntemp, fw_ver, hw_ver):
        """Add a new slave if there is room"""
        if len(self._slaves) >= self.MAX_NR_OF_SLAVES:
            self.log.warn(f"Cannot add more than {self.MAX_NR_OF_SLAVES} slaves")
            return None
        elif self.is_known(mac):
            self.log.warn(f"Slave with MAC {self.log.mac_to_str(mac)} already known")
            return None
        elif addr == self.get_by_addr(addr):
            self.log.warn(f"Slave with address {addr} already known")
            return None
        else:
            self.log.info(f"Add slave {self.log.mac_to_str(mac)} to list")
            new = virt_slave(self, mac, addr, ncell, ntemp, fw_ver, hw_ver)
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
                self.log.info(f"Remove slave {self.log.mac_to_str(info.mac)} from list")
                del self._slaves[i]        # keep a hole – list stays compact
                return True
        self.log.warn(f"Unable to remove slave {self.log.mac_to_str(info.mac)} from list")
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
    def __init__(self, mac, addr, ncell, ntemp, fw_ver, hw_ver):
        self.battery = battery()
        self.battery.info.update_all(mac=mac, addr=addr, ncell=ncell, ntemp=ntemp, fw_ver=fw_ver, hw_ver=hw_ver)

    
