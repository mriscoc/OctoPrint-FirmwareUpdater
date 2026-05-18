import argparse
import os
import sys
import time

import serial

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from octoprint_firmwareupdater.methods import MarlinBinaryProtocol


class ConsoleLogger:
    def __init__(self, debug_enabled=False):
        self.debug_enabled = debug_enabled
        self._progress_active = False

    def _write_normal(self, prefix, message):
        if self._progress_active:
            print()
            self._progress_active = False
        print(f"{prefix}{message}")

    def debug(self, message, *args, **kwargs):
        if self.debug_enabled:
            self._write_normal("[Debug] ", message)

    def info(self, message, *args, **kwargs):
        if isinstance(message, str) and message.startswith("PROGRESS:"):
            print(f"\r{message}", end="", flush=True)
            self._progress_active = True
            return

        self._write_normal("", message)

    def warning(self, message, *args, **kwargs):
        self._write_normal("[Warning] ", message)

    def error(self, message, *args, **kwargs):
        self._write_normal("[Error] ", message)

    def critical(self, message, *args, **kwargs):
        self._write_normal("[Critical] ", message)

    def exception(self, message, *args, **kwargs):
        self._write_normal("[Exception] ", message)


def _configure_simulation(simulate_errors):
    MarlinBinaryProtocol.Protocol.simerr = float(simulate_errors)


def test_protocol(port, baudrate, blocksize, timeout, simulate_errors, debug_enabled):
    _configure_simulation(simulate_errors)
    logger = ConsoleLogger(debug_enabled)
    protocol = None

    try:
        print(f"Opening protocol on {port} @ {baudrate}")
        protocol = MarlinBinaryProtocol.Protocol(port, baudrate, blocksize, int(timeout), logger)

        print("Connecting to Marlin binary protocol...")
        protocol.connect()
        print("Protocol handshake OK")

        print("Querying File Transfer capability...")
        filetransfer = MarlinBinaryProtocol.FileTransferProtocol(protocol, logger=logger)
        if filetransfer.connect() is False:
            print("File Transfer capability query failed")
            return 1

        print("File Transfer query OK")
        print(f"Version: {getattr(filetransfer, 'version', 'unknown')}")
        print(f"Compression: {getattr(filetransfer, 'compression', {})}")

        protocol.send_ascii_no_wait("M117 MarlinBinaryProtocol test OK")
        return 0

    except MarlinBinaryProtocol.FatalError:
        print("FatalError: protocol reported a fatal error")
        return 2
    except Exception as exc:
        print(f"Protocol test failed: {exc}")
        return 1
    finally:
        if protocol is not None:
            try:
                protocol.disconnect()
            except Exception:
                pass
            try:
                protocol.shutdown()
            except Exception:
                pass


def upload_file(port, baudrate, source, destination, blocksize, timeout, compression, simulate_errors, debug_enabled):
    _configure_simulation(simulate_errors)
    logger = ConsoleLogger(debug_enabled)
    protocol = None
    filetransfer = None
    disconnected = False

    try:
        print(f"Opening protocol on {port} @ {baudrate}")
        protocol = MarlinBinaryProtocol.Protocol(port, baudrate, blocksize, int(timeout), logger)

        print("Connecting to Marlin binary protocol...")
        protocol.connect()
        print("Protocol handshake OK")

        filetransfer = MarlinBinaryProtocol.FileTransferProtocol(protocol, logger=logger)
        target_name = destination or os.path.basename(source)

        print(f"Uploading {source} -> {target_name}")
        filetransfer.copy(source, target_name, compression, False)
        print("Upload complete")

        protocol.disconnect()
        disconnected = True
        protocol.send_ascii_no_wait("M117 MarlinBinaryProtocol upload OK")
        time.sleep(1)
        protocol.send_ascii_no_wait("M21")
        return 0

    except MarlinBinaryProtocol.FatalError:
        print("FatalError: protocol reported a fatal error")
        return 2
    except FileNotFoundError as exc:
        print(f"Source file not found: {exc}")
        return 1
    except serial.SerialException as exc:
        print(f"Serial error: {exc}")
        return 1
    except Exception as exc:
        print(f"Upload failed: {exc}")
        if filetransfer is not None:
            try:
                filetransfer.abort()
            except Exception:
                pass
        return 1
    finally:
        if protocol is not None:
            if not disconnected:
                try:
                    protocol.disconnect()
                except Exception:
                    pass
            try:
                protocol.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Standalone Marlin Binary Protocol tests")
    parser.add_argument("source", nargs="?", help="Source file to transfer. If omitted, runs protocol test only")
    parser.add_argument("--port", default="COM3", help="Serial port (e.g. COM3)")
    parser.add_argument("--baud", type=int, default=250000, help="Baudrate")
    parser.add_argument("--destination", default="", help="Destination filename on the client")
    parser.add_argument("--blocksize", type=int, default=512, help="Protocol block size")
    parser.add_argument("--timeout", type=int, default=1000, help="Protocol timeout in ms")
    parser.add_argument("--no-compression", action="store_true", help="Disable compression")
    parser.add_argument("--simulate-errors", type=float, default=0.0, help="Simulated corruption ratio")
    parser.add_argument("--debug", action="store_true", help="Show debug messages")

    args = parser.parse_args()

    if args.source is None:
        raise SystemExit(test_protocol(args.port, args.baud, args.blocksize, args.timeout, args.simulate_errors, args.debug))

    raise SystemExit(
        upload_file(
            args.port,
            args.baud,
            args.source,
            args.destination,
            args.blocksize,
            args.timeout,
            not args.no_compression,
            args.simulate_errors,
            args.debug,
        )
    )
