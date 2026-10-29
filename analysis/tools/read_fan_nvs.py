# Print only the FAN settings from the stock NVS partition (no credentials).
#
# Read just the NVS (16 KiB, a few seconds even at 115200):
#   esptool --chip esp32s3 --port PORT --before no_reset read-flash 0x9000 0x4000 nvs.bin
#   python3 read_fan_nvs.py nvs.bin
# A full 16 MB dump works too; the NVS is taken from offset 0x9000.
import struct, sys

data = open(sys.argv[1], "rb").read()
nvs = data[0x9000:0xD000] if len(data) > 0x4000 else data
namespaces, values = {}, {}
for p in range(0, len(nvs), 4096):
    page = nvs[p:p + 4096]
    if page[:4] == b"\xff\xff\xff\xff":
        continue
    seq = struct.unpack("<I", page[4:8])[0]
    bitmap = page[32:64]
    e = 0
    while e < 126:
        state = (bitmap[e // 4] >> ((e % 4) * 2)) & 3
        ent = page[64 + e * 32:64 + (e + 1) * 32]
        ns, typ, span = ent[0], ent[1], max(ent[2], 1)
        if state != 2:  # only written entries
            e += 1
            continue
        key = ent[8:24].split(b"\0")[0].decode(errors="replace")
        if ns == 0 and typ == 0x01:
            namespaces[ent[24]] = key
        elif typ in (0x04, 0x14):
            new = (seq, e, struct.unpack("<i" if typ == 0x14 else "<I", ent[24:28])[0])
            if (ns, key) not in values or new[:2] > values[(ns, key)][:2]:
                values[(ns, key)] = new  # newest page wins
        e += span

fan = [ns for ns, name in namespaces.items() if name == "FAN"]
if not fan:
    sys.exit("no FAN namespace found")
for (ns, key), (_, _, v) in sorted(values.items()):
    if ns == fan[0]:
        extra = f"  ({v // 60:02d}:{v % 60:02d})" if key.startswith("FANTIME") else ""
        print(f"{key:16} {v}{extra}")
