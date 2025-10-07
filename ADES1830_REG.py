import json
import gc

class REGISTER:
    MAX_VALUE = 0xFFFFFFFFFFFF
    MAX_ADDRESS = 0xFFFF

    def __init__(self, read_address, write_address, name, is_read_only=False, hal=None):
        if read_address > self.MAX_ADDRESS or (write_address is not None and write_address > self.MAX_ADDRESS):
            raise ValueError("Address exceeds 16-bit max")
        self.read_address = read_address
        self.write_address = write_address
        self.name = name
        self.value = 0
        self.is_read_only = is_read_only or write_address is None
        self.hal = hal

    def read(self):
        if self.hal:
            self.value = self.hal.read(self.read_address)
        return self.value

    def write(self, value):
        if self.is_read_only or self.write_address is None:
            raise ValueError("Cannot write to read-only register")
        self.value = value & self.MAX_VALUE
        if self.hal:
            self.hal.write(self.write_address, self.value)

    def get_bits(self, bit_start, width):
        mask = (1 << width) - 1
        return (self.value >> bit_start) & mask

    def set_bits(self, bit_start, width, field_value):
        if self.is_read_only or self.write_address is None:
            raise ValueError("Cannot write to read-only register")
        mask = (1 << width) - 1
        if field_value > mask:
            raise ValueError("Field value exceeds width")
        self.value &= ~(mask << bit_start)
        self.value |= (field_value & mask) << bit_start
        self.value &= self.MAX_VALUE
        if self.hal:
            self.hal.write(self.write_address, self.value)

def create_register_class(name, read_address, write_address, fields, is_read_only=False):
    # Validate fields
    for field_name, field_info in fields.items():
        bit_start = field_info.get("bit_start")
        width = field_info.get("width")
        default = field_info.get("default", 0)
        if isinstance(default, str) and default.startswith("0x"):
            try:
                default = int(default, 16)
            except ValueError:
                raise ValueError(f"Invalid hex default for {field_name}: {default}")
        if not isinstance(bit_start, int) or not isinstance(width, int):
            raise ValueError(f"Invalid field {field_name}")
        if bit_start + width > 48:
            raise ValueError(f"Field {field_name} exceeds 48-bit register")
        if width < 1:
            raise ValueError(f"Field {field_name} width must be positive")
        if default > ((1 << width) - 1):
            raise ValueError(f"Field {field_name} default exceeds width")

    # Check for field overlaps
    field_items = list(fields.items())
    for i in range(len(field_items)):
        for j in range(i + 1, len(field_items)):
            f1, info1 = field_items[i]
            f2, info2 = field_items[j]
            s1, w1 = info1["bit_start"], info1["width"]
            s2, w2 = info2["bit_start"], info2["width"]
            if s1 <= s2 < s1 + w1 or s2 <= s1 < s2 + w2:
                raise ValueError(f"Overlapping fields: {f1} and {f2}")

    # Compute initial value
    initial_value = 0
    for field_name, field_info in fields.items():
        default = field_info.get("default", 0)
        if isinstance(default, str) and default.startswith("0x"):
            default = int(default, 16)
        initial_value |= (default & ((1 << field_info["width"]) - 1)) << field_info["bit_start"]
    if initial_value > REGISTER.MAX_VALUE:
        raise ValueError("Combined default exceeds 48-bit max")

    class NewRegister(REGISTER):
        def __init__(self, hal=None):
            super().__init__(read_address, write_address, name, is_read_only, hal)
            self.fields = fields
            self.value = initial_value & self.MAX_VALUE

    # Add getters and setters
    for field_name, field_info in fields.items():
        bit_start = field_info["bit_start"]
        width = field_info["width"]
        def getter(self, bit_start=bit_start, width=width):
            return self.get_bits(bit_start, width)
        setattr(NewRegister, f"get_{field_name}", getter)
        if not is_read_only and write_address is not None:
            def setter(self, value, bit_start=bit_start, width=width):
                self.set_bits(bit_start, width, value)
            setattr(NewRegister, f"set_{field_name}", setter)

    gc.collect()
    return NewRegister

class RegisterMap:
    def __init__(self, json_file, hal=None):
        """Initialize register map from JSON file."""
        self.registers = {}
        self.hal = hal
        self.load_json(json_file)

    def load_json(self, json_file):
        """Load and parse JSON file with manual validation."""
        try:
            with open(json_file, "r") as f:
                register_configs = json.load(f)
        except (OSError, ValueError):
            raise ValueError(f"Failed to load {json_file}")

        for config in register_configs:
            if not isinstance(config, dict):
                raise ValueError("Invalid register config")
            name = config.get("name")
            read_address = config.get("read_address")
            write_address = config.get("write_address")
            is_read_only = config.get("is_read_only", False)
            fields = config.get("fields", {})
            if not all([name, read_address is not None, isinstance(fields, dict)]):
                raise ValueError(f"Invalid config for {name}")
            if isinstance(read_address, str) and read_address.startswith("0x"):
                read_address = int(read_address, 16)
            elif isinstance(read_address, str):
                raise ValueError(f"Invalid read_address format for {name}")
            if read_address > REGISTER.MAX_ADDRESS:
                raise ValueError(f"read_address for {name} exceeds 16-bit max")
            if write_address is not None:
                if isinstance(write_address, str) and write_address.startswith("0x"):
                    write_address = int(write_address, 16)
                elif isinstance(write_address, str):
                    raise ValueError(f"Invalid write_address format for {name}")
                if write_address > REGISTER.MAX_ADDRESS:
                    raise ValueError(f"write_address for {name} exceeds 16-bit max")
            self.registers[name] = create_register_class(
                name=name,
                read_address=read_address,
                write_address=write_address,
                fields=fields,
                is_read_only=is_read_only
            )
        gc.collect()

    def get_register(self, name, hal=None):
        """Instantiate a register with optional HAL override."""
        if name not in self.registers:
            raise ValueError(f"Register {name} not found")
        return self.registers[name](hal=hal or self.hal)