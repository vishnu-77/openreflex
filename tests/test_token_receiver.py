import socket
import threading
from http.server import ThreadingHTTPServer

import pytest

from openreflex.usage import HOST, PORT, _Handler, receiver_running, stop_receiver


@pytest.fixture
def running_receiver():
    if receiver_running():
        pytest.skip(f"something is already answering on {HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_receiver_running_identifies_the_real_receiver(running_receiver):
    assert receiver_running() is True


def test_receiver_running_rejects_an_unrelated_listener_on_the_same_port():
    if receiver_running():
        pytest.skip(f"something is already answering on {HOST}:{PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(1)
    try:
        assert receiver_running() is False
    finally:
        sock.close()


def test_stop_receiver_actually_shuts_it_down(running_receiver):
    assert receiver_running() is True
    stop_receiver()
    assert receiver_running() is False
