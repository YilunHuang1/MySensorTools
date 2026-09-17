from sensor_tools.uwb_serial import packet_tlvs, ranging


class PacketParser:
    @staticmethod
    def parse_all(data_bytes):
        return [ranging(value) for kind, value in packet_tlvs(data_bytes) if kind == 0xC5]

    @staticmethod
    def parse(data_bytes):
        """Legacy single-result API; new callers should process every C5 TLV."""
        results = PacketParser.parse_all(data_bytes)
        return results[0] if results else None

    parseRangingPacket = parse
