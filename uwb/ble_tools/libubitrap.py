#!/usr/bin/env python3
"""Serial-only UWB bench entry point using the shared standalone implementation."""
import argparse
import time
from CmdBuilder import CmdBuilder, CmdEnum
from SerialHandlerStandalone import SerialHandler

_handler = None


def startSerial(port='/dev/ttyUSB0', *, allow_control=False):
    global _handler
    if _handler is not None:
        raise RuntimeError('serial handler already started')
    _handler = SerialHandler(port=port, allow_control=allow_control)
    try:
        _handler.start()
    except Exception:
        _handler.stop()
        _handler = None
        raise
    return _handler


def closeSerial():
    global _handler
    if _handler is not None:
        _handler.stop()
        _handler = None


def process_packets(*unused):
    if _handler is None:
        raise RuntimeError('startSerial must be called first')
    return _handler.process_packets()


def sendCmd(command):
    if _handler is None:
        raise RuntimeError('startSerial must be called first')
    _handler.sendCmd(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--duration', type=float, default=10)
    parser.add_argument('--command', choices=['version', 'apple-fira'])
    parser.add_argument('--shared-config-hex', help='Apple Nearby Interaction shared configuration, including type byte')
    parser.add_argument('--allow-device-control', action='store_true')
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error('duration must be positive')
    if args.command and not args.allow_device_control:
        parser.error('serial commands require --allow-device-control on an isolated bench device')
    if args.command == 'apple-fira' and not args.shared_config_hex:
        parser.error('apple-fira requires --shared-config-hex from the current phone session')
    try:
        handler = startSerial(args.port, allow_control=args.allow_device_control)
        if args.command == 'version':
            sendCmd(CmdBuilder.build(CmdEnum.GET_VERSION))
        elif args.command == 'apple-fira':
            packet, session = CmdBuilder.build(CmdEnum.SET_APPLE_FIRA, bytes.fromhex(args.shared_config_hex))
            handler.session_id = session
            sendCmd(packet)
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline and not handler.quit:
            process_packets()
            time.sleep(.01)
    finally:
        closeSerial()


if __name__ == '__main__':
    main()
