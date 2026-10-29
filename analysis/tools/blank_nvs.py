# Blank the NVS partition (Wi-Fi credentials, Omlet API token, device keys) in a
# full flash dump before sharing it. Reads the partition table from 0x8000.
# usage: python3 blank_nvs.py omlet-fan-backup.bin omlet-fan-shareable.bin
import struct, sys

data = bytearray(open(sys.argv[1], "rb").read())
for off in range(0x8000, 0x8C00, 32):
    entry = data[off:off + 32]
    if entry[:2] != b"\xaa\x50":
        break
    ptype, subtype, start, size = struct.unpack("<BBII", entry[2:12])
    name = entry[12:28].split(b"\0")[0].decode()
    if ptype == 1 and subtype == 2:  # data / nvs
        data[start:start + size] = b"\xff" * size
        print(f"blanked {name} at {start:#x} ({size:#x} bytes)")
open(sys.argv[2], "wb").write(data)
