"""Tests for local_forward: a loopback TCP forwarder.

Run with: python3 -m unittest test_local_forward
"""

import asyncio
import socket
import threading
import unittest

import local_forward


class Loop:
    """An asyncio loop on a thread, to host servers under test."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(10)

    def close(self):
        async def cancel_all():
            me = asyncio.current_task()
            pending = [t for t in asyncio.all_tasks() if t is not me]
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        self.run(cancel_all())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


async def start_echo():
    async def handle(r, w):
        while data := await r.read(65536):
            w.write(data.upper())
            await w.drain()
        w.close()

    return await asyncio.start_server(handle, "127.0.0.1", 0)


def port_of(server):
    return server.sockets[0].getsockname()[1]


class ForwardTests(unittest.TestCase):
    def setUp(self):
        self.loop = Loop()
        self.addCleanup(self.loop.close)
        self.echo = self.loop.run(start_echo())
        self.fwd = self.loop.run(
            local_forward.start(0, "127.0.0.1", port_of(self.echo))
        )

    def connect(self):
        return socket.create_connection(("127.0.0.1", port_of(self.fwd)), timeout=5)

    def test_bytes_go_through_both_ways(self):
        with self.connect() as s:
            s.sendall(b"hello")
            self.assertEqual(s.recv(100), b"HELLO")

    def test_several_connections_at_once(self):
        a, b = self.connect(), self.connect()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        a.sendall(b"aaa")
        b.sendall(b"bbb")
        self.assertEqual(b.recv(100), b"BBB")
        self.assertEqual(a.recv(100), b"AAA")

    def test_large_payload_is_not_truncated(self):
        payload = b"x" * 500_000
        with self.connect() as s:
            s.sendall(payload)
            got = b""
            while len(got) < len(payload):
                chunk = s.recv(65536)
                if not chunk:
                    break
                got += chunk
        self.assertEqual(got, payload.upper())

    def test_listens_on_loopback_only(self):
        self.assertEqual(self.fwd.sockets[0].getsockname()[0], "127.0.0.1")

    def test_unreachable_target_closes_the_client_and_keeps_serving(self):
        dead = socket.socket()
        dead.bind(("127.0.0.1", 0))
        dead_port = dead.getsockname()[1]
        dead.close()  # nothing listens here now
        fwd = self.loop.run(local_forward.start(0, "127.0.0.1", dead_port))
        with socket.create_connection(("127.0.0.1", port_of(fwd)), timeout=5) as s:
            s.sendall(b"x")
            self.assertEqual(s.recv(10), b"")
        # the working forwarder is unaffected
        with self.connect() as s:
            s.sendall(b"ok")
            self.assertEqual(s.recv(10), b"OK")


class ParseTargetTests(unittest.TestCase):
    def test_host_and_port(self):
        self.assertEqual(local_forward.parse_target("192.168.1.2:443"), ("192.168.1.2", 443))

    def test_hostname(self):
        self.assertEqual(local_forward.parse_target("authors.example.org:8443"), ("authors.example.org", 8443))

    def test_bad_targets_are_value_errors(self):
        for bad in ("nohost", ":443", "h:", "h:abc", "h:0", "h:70000", ""):
            with self.assertRaises(ValueError, msg=bad):
                local_forward.parse_target(bad)


if __name__ == "__main__":
    unittest.main()
