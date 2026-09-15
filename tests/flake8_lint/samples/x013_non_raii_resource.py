"""Sample file demonstrating X013 non-RAII subprocess/socket resource violations."""

import socket
import subprocess


def launch_process() -> None:
    """Launch a subprocess without RAII so X013 is triggered."""
    proc = subprocess.Popen(["echo", "hello"], stdout=subprocess.PIPE)
    proc.communicate()


def open_socket() -> None:
    """Open a socket without RAII so X013 is triggered."""
    sock = socket.socket()
    sock.close()