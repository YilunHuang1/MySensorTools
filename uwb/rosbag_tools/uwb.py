#!/usr/bin/env python3
"""Preserve an MCAP recording and add distance/angular acceleration channels.

ROS CDR and Aorta FlatBuffers ranging inputs are supported. Derived Float64 CDR
channels are readable by Foxglove without a robot-side ROS installation. Angular
acceleration is deg/s²; distance acceleration follows the input distance unit/s².
"""
import argparse
import math
import os
from pathlib import Path
import struct
import tempfile

from mcap.reader import make_reader
from mcap.writer import Writer
from sensor_tools.mcap import Decoder, Record, channels as list_channels, topic_matches, uwb_fields


class Derivative:
    def __init__(self, circular=False):
        self.circular = circular
        self.previous = None
        self.velocity = None
        self.previous_dt = None

    def update(self, value, timestamp_ns):
        if not math.isfinite(value):
            raise ValueError('nonfinite ranging value')
        if self.previous is None:
            self.previous = (value, timestamp_ns)
            return None
        previous_value, previous_time = self.previous
        dt = (timestamp_ns - previous_time) / 1e9
        # A duplicated/reordered timestamp does not establish a new derivative interval.
        if dt <= 1e-6:
            return None
        delta = value - previous_value
        if self.circular:
            delta = (delta + 180.) % 360. - 180.
        velocity = delta / dt
        acceleration = None if self.velocity is None else 2 * (velocity - self.velocity) / (dt + self.previous_dt)
        self.previous = (value, timestamp_ns)
        self.velocity, self.previous_dt = velocity, dt
        return acceleration


def process(input_path, output_path, topic='/uwb/data'):
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError('input and output must be different')
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    derived_topics = {
        'distance_filtered': '/uwb/derived/dist_accel',
        'angle': '/uwb/derived/angle_accel_raw',
        'angle_filtered': '/uwb/derived/angle_accel_filtered',
    }
    if any(channel.topic in derived_topics.values() for channel in list_channels(input_path)):
        raise ValueError('derived channel already exists in input')
    fd, temporary = tempfile.mkstemp(prefix='.uwb-derived-', dir=output_path.parent)
    count, derived_count = 0, 0
    try:
        with input_path.open('rb') as stream, os.fdopen(fd, 'wb') as out:
            reader, writer = make_reader(stream), Writer(out)
            writer.start()
            sid = writer.register_schema(name='std_msgs/msg/Float64', encoding='ros2msg', data=b'float64 data\n')
            derived = {field: writer.register_channel(name, 'cdr', sid,
                        metadata={'unit': 'deg/s^2' if field != 'distance_filtered' else 'input_distance_unit/s^2',
                                  'timestamp_basis': 'source timestamp, else MCAP publish_time'})
                       for field, name in derived_topics.items()}
            schemas, channels, states = {}, {}, {}
            summary = reader.get_summary()
            if summary:
                for schema in summary.schemas.values():
                    schemas[schema.id] = writer.register_schema(schema.name, schema.encoding, schema.data)
                for channel in summary.channels.values():
                    channels[channel.id] = writer.register_channel(channel.topic, channel.message_encoding,
                        schemas.get(channel.schema_id, 0), metadata=channel.metadata)
            decoder = Decoder()
            selected_source = None
            for schema, channel, message in reader.iter_messages(log_time_order=False):
                if channel.topic in derived_topics.values():
                    raise ValueError(f'derived channel already exists: {channel.topic}')
                if schema and schema.id not in schemas:
                    schemas[schema.id] = writer.register_schema(schema.name, schema.encoding, schema.data)
                if channel.id not in channels:
                    channels[channel.id] = writer.register_channel(channel.topic, channel.message_encoding,
                        schemas.get(channel.schema_id, 0), metadata=channel.metadata)
                writer.add_message(channels[channel.id], message.log_time, message.data,
                                   message.publish_time, message.sequence)
                count += 1
                if not topic_matches(channel.topic, topic):
                    continue
                if selected_source is not None and selected_source != channel.topic:
                    raise ValueError('multiple ranging sources match; pass one exact --topic')
                selected_source = channel.topic
                record = Record(channel.topic, schema.name if schema else '', channel.message_encoding,
                                message.log_time, message.publish_time, decoder.decode(schema, channel, message.data))
                row = uwb_fields(record)
                # Keep each recorded source separate when a file contains multiple publishers/groups.
                state = states.setdefault(channel.id, {field: Derivative(field != 'distance_filtered')
                                                        for field in derived_topics})
                for field, calculator in state.items():
                    value = calculator.update(float(row[field]), row['timestamp_ns'])
                    if value is not None:
                        writer.add_message(derived[field], message.log_time,
                            b'\x00\x01\x00\x00' + struct.pack('<d', value),
                            row['timestamp_ns'], message.sequence)
                        derived_count += 1
            for item in reader.iter_metadata():
                writer.add_metadata(item.name, item.metadata)
            for item in reader.iter_attachments():
                writer.add_attachment(item.create_time, item.log_time, item.name, item.media_type, item.data)
            if not derived_count:
                raise ValueError('need at least three valid ranging samples with increasing timestamps')
            writer.finish()
        Path(temporary).replace(output_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return count, derived_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input_bag')
    parser.add_argument('output_bag')
    parser.add_argument('--topic', default='/uwb/data')
    args = parser.parse_args()
    try:
        count, derived = process(args.input_bag, args.output_bag, args.topic)
        print(f'Preserved {count} messages; added {derived} derived messages -> {args.output_bag}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
