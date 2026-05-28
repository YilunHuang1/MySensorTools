import argparse
import binascii
import re


HEADER_SIZE = 32


def parse_eeprom_data(raw_hex_str):
    """Parse SC230AI stereo EEPROM bytes from i2ctransfer-style hex output."""
    hex_tokens = re.findall(r"0x[0-9a-fA-F]{2}", raw_hex_str)
    if hex_tokens:
        clean_hex = "".join(token[2:] for token in hex_tokens)
    else:
        clean_hex = "".join(raw_hex_str.split()).replace("0x", "")

    hex_bytes = bytes.fromhex(clean_hex)
    result = {}
    total_len = len(hex_bytes)

    def read_byte(offset):
        return hex_bytes[offset] if offset < total_len else None

    def read_slice(offset, size):
        return hex_bytes[offset:min(offset + size, total_len)] if offset < total_len else b""

    def printable(byte):
        return 32 <= byte <= 126

    check_0 = read_byte(0)
    result["check_0"] = check_0
    print(f"[1] head check_0: {check_0:#04x}" if check_0 is not None else "[1] head check_0: <missing>")

    header_bytes = read_slice(1, HEADER_SIZE)
    result["header"] = header_bytes
    print(f"[2] EEPROM header ({len(header_bytes)} bytes): {binascii.hexlify(header_bytes, sep=' ').decode().upper()}")
    if header_bytes:
        header_ascii = "".join(chr(b) if printable(b) else "." for b in header_bytes)
        print(f"    ASCII: {header_ascii}")

    # Some samples place SN at offset 395; older dumps are less stable, so fall back
    # to the longest printable run. This keeps the parser usable across revisions.
    sn_fixed = read_slice(395, 32)
    fixed_score = sum(1 for byte in sn_fixed if printable(byte))
    use_fixed = len(sn_fixed) >= 8 and fixed_score >= max(8, len(sn_fixed) // 2)

    if use_fixed:
        sn_bytes = sn_fixed
    else:
        best_start = -1
        best_len = 0
        start = None
        length = 0
        for i, byte in enumerate(hex_bytes):
            if printable(byte):
                if start is None:
                    start = i
                    length = 1
                else:
                    length += 1
            else:
                if length >= 8 and start is not None and (length > best_len or (length == best_len and start > best_start)):
                    best_start = start
                    best_len = length
                start = None
                length = 0
        if length >= 8 and start is not None and (length > best_len or (length == best_len and start > best_start)):
            best_start = start
            best_len = length
        sn_bytes = hex_bytes[best_start:best_start + best_len] if best_len >= 8 else b""

    result["sn"] = sn_bytes[:32]
    sn_str = "".join(chr(byte) if printable(byte) else "" for byte in sn_bytes).strip()
    print(f"[3] serial number ({len(sn_bytes)} bytes):")
    print(f"    raw: {binascii.hexlify(sn_bytes[:32], sep=' ').decode().upper()}")
    print(f"    ascii: '{sn_str}'")

    return result


def main():
    parser = argparse.ArgumentParser(description="Parse stereo camera EEPROM hex dump")
    parser.add_argument("-f", "--file", help="Text file containing 0xXX hex bytes")
    parser.add_argument("--hex", dest="hex_string", help="Inline EEPROM hex string")
    parser.add_argument("--interactive", action="store_true", help="Read hex strings interactively")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            parse_eeprom_data(f.read())
        return

    if args.hex_string:
        parse_eeprom_data(args.hex_string)
        return

    if not args.interactive:
        parser.error("use --file, --hex, or --interactive")

    while True:
        user_input = input("EEPROM hex> ").strip()
        if user_input.lower() == "exit":
            break
        if user_input:
            parse_eeprom_data(user_input)


if __name__ == "__main__":
    main()
