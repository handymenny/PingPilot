from __future__ import annotations

import os
import signal
import subprocess  # nosec B404
import threading
from collections.abc import Sequence


_active_processes: set[subprocess.Popen[str]] = set()
_process_lock = threading.Lock()


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def terminate_active_processes() -> None:
    with _process_lock:
        for process in tuple(_active_processes):
            _terminate_process(process)


def install_shutdown_handler() -> None:
    def handle_shutdown(signum: int, _frame: object) -> None:
        terminate_active_processes()
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)


def run(
    args: Sequence[str],
    *,
    capture_output: bool,
    text: bool,
    timeout: float,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )  # nosec B603
    else:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            start_new_session=True,
        )  # nosec B603
    with _process_lock:
        _active_processes.add(process)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process(process)
            stdout, stderr = process.communicate()
            raise
    finally:
        with _process_lock:
            _active_processes.discard(process)

    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    if check and result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode, args, output=stdout, stderr=stderr
        )
    return result
