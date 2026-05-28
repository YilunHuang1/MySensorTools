from pathlib import Path
import argparse
import struct

DEFAULT_TOPIC_MAPPING = {
    '/x5/vlog': 'x5_vlog.txt',
    '/s100/vlog': 's100_vlog.txt',
}

def get_log_level_str(level):
    if level == 10: return "DEBUG"
    if level == 20: return "INFO"
    if level == 30: return "WARN"
    if level == 40: return "ERROR"
    if level == 50: return "FATAL"
    return str(level)

def extract_logs(bag_file: str, output_dir: str, topic_mapping: dict[str, str]):
    try:
        from mcap.reader import make_reader
    except ImportError:
        print("缺少依赖: 请安装 'mcap' 后重试")
        return

    bag_path = Path(bag_file)
    if not bag_path.exists():
        print(f"文件不存在: {bag_file}")
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    file_handles = {
        topic: open(output_path / filename, 'w')
        for topic, filename in topic_mapping.items()
    }

    print(f"开始处理: {bag_path} ...")
    count = 0

    def _align(offset: int, align_bytes: int) -> int:
        return offset + ((align_bytes - (offset % align_bytes)) % align_bytes)

    def _read_int32(buf: bytes, offset: int):
        offset = _align(offset, 4)
        return struct.unpack_from("<i", buf, offset)[0], offset + 4

    def _read_uint32(buf: bytes, offset: int):
        offset = _align(offset, 4)
        return struct.unpack_from("<I", buf, offset)[0], offset + 4

    def _read_uint8(buf: bytes, offset: int):
        return struct.unpack_from("<B", buf, offset)[0], offset + 1

    def _read_string(buf: bytes, offset: int):
        length, offset = _read_uint32(buf, offset)
        s_bytes = buf[offset : offset + length]
        s = s_bytes.decode("utf-8", errors="ignore").replace("\x00", "")
        return s, offset + length

    def parse_log_cdr(data: bytes):
        try:
            if len(data) < 4:
                return None
            offset = 4
            sec, offset = _read_int32(data, offset)
            nsec, offset = _read_uint32(data, offset)
            level, offset = _read_uint8(data, offset)
            offset = _align(offset, 4)
            name, offset = _read_string(data, offset)
            msg, offset = _read_string(data, offset)
            file, offset = _read_string(data, offset)
            function, offset = _read_string(data, offset)
            line, offset = _read_uint32(data, offset)
            return {
                "sec": sec,
                "nsec": nsec,
                "level": level,
                "name": name,
                "msg": msg,
                "file": file,
                "function": function,
                "line": line,
            }
        except Exception:
            return None

    with open(bag_path, "rb") as f:
        reader = make_reader(f)
        for topic in topic_mapping.keys():
            for _, _, message in reader.iter_messages(topics=[topic]):
                rec = parse_log_cdr(message.data)
                if not rec:
                    continue
                time_str = f"{int(rec['sec'])}.{int(rec['nsec']):09d}"
                level_str = get_log_level_str(int(rec['level']))
                log_line = f"[{time_str}] [{level_str}] [{rec['name']}]: {rec['msg']}\n"
                file_handles[topic].write(log_line)
                count += 1
                if count % 10000 == 0:
                    print(f"已处理 {count} 条日志...")

    for f in file_handles.values():
        f.close()

    print(f"处理完成！共提取 {count} 条日志。")
    print(f"日志已保存到: {output_path.resolve()}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='从 MCAP 中提取 ROS 日志 topic')
    parser.add_argument('mcap', help='输入 MCAP 文件')
    parser.add_argument('-o', '--output-dir', default='logs', help='输出目录')
    parser.add_argument(
        '--topic',
        action='append',
        default=[],
        metavar='TOPIC=FILE',
        help='自定义 topic 到输出文件的映射，可重复传入，例如 /x5/vlog=x5.txt'
    )
    args = parser.parse_args()

    mapping = DEFAULT_TOPIC_MAPPING
    if args.topic:
        mapping = {}
        for item in args.topic:
            topic, sep, filename = item.partition('=')
            if not sep or not topic or not filename:
                parser.error(f'无效 --topic 映射: {item}')
            mapping[topic] = filename

    extract_logs(args.mcap, args.output_dir, mapping)
