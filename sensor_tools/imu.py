"""IMU samples from MCAP files and legacy ROS2 bag directories."""
from pathlib import Path
from .mcap import Record, iter_records, imu_fields, plain, source_time_ns, topic_matches


def iter_imu(path, topic='imu_raw'):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    files = sorted(path.glob('*.mcap')) if path.is_dir() else [path]
    if files and all(file.suffix == '.mcap' for file in files):
        for file in files:
            for record in iter_records(file, [topic]):
                stamp, frame, gyro, accel = imu_fields(record)
                yield record.log_time_ns, stamp, frame, gyro, accel
        return
    from rosbags.highlevel import AnyReader
    from rosbags.typesys import Stores, get_typestore
    with AnyReader([path], default_typestore=get_typestore(Stores.ROS2_HUMBLE)) as reader:
        connections = [c for c in reader.connections if topic_matches(c.topic, topic)]
        for connection, timestamp, raw in reader.messages(connections=connections):
            data = plain(reader.deserialize(raw, connection.msgtype))
            record = Record(connection.topic, connection.msgtype, 'cdr', timestamp,
                            source_time_ns(data, timestamp), data)
            stamp, frame, gyro, accel = imu_fields(record)
            yield timestamp, stamp, frame, gyro, accel
