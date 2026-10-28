"""local_forward forwards a port on this machine's loopback to another host.

It exists so harvest.py -local, which talks to https://127.0.0.1:5000, can
reach a CaltechAUTHORS that is not on this machine: a Multipass VM or an AWS
test instance. It copies bytes and does not touch the TLS inside them.

  python3 local_forward.py [-p PORT] HOST:PORT

  -p PORT   the loopback port to listen on (default 5000)

It listens on 127.0.0.1 only, never on another interface. Stop it with ^C.
Exit status: 0 stopped, 2 usage, 73 the port is in use or cannot be opened.
"""

import asyncio
import sys

DEFAULT_PORT = 5000


def parse_target(text):
    """Return (host, port) from "HOST:PORT", or raise ValueError."""
    host, sep, port = text.rpartition(":")
    if not sep or not host or not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError(f"expected HOST:PORT, got {text!r}")
    return host, int(port)


async def _copy(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except OSError:
        pass
    finally:
        writer.close()


async def _handle(client_r, client_w, host, port):
    try:
        target_r, target_w = await asyncio.open_connection(host, port)
    except OSError as e:
        print(f"local_forward: cannot reach {host}:{port}: {e}", file=sys.stderr)
        client_w.close()
        return
    await asyncio.gather(_copy(client_r, target_w), _copy(target_r, client_w))


async def start(listen_port, host, port):
    """Start forwarding 127.0.0.1:listen_port to host:port; return the server.

    A listen_port of 0 picks a free port; read it from server.sockets.
    """
    return await asyncio.start_server(
        lambda r, w: _handle(r, w, host, port), "127.0.0.1", listen_port
    )


async def _main(listen_port, host, port):
    server = await start(listen_port, host, port)
    print(f"forwarding https://127.0.0.1:{listen_port} -> {host}:{port} (^C stops)")
    async with server:
        await server.serve_forever()


def main(argv):
    listen_port = DEFAULT_PORT
    args = list(argv)
    try:
        if args[:1] == ["-p"]:
            listen_port = int(args[1])
            args = args[2:]
        if len(args) != 1:
            raise ValueError("expected exactly one HOST:PORT")
        host, port = parse_target(args[0])
    except (ValueError, IndexError) as e:
        print(f"usage: local_forward.py [-p PORT] HOST:PORT ({e})", file=sys.stderr)
        return 2
    try:
        asyncio.run(_main(listen_port, host, port))
    except KeyboardInterrupt:
        return 0
    except OSError as e:
        print(f"local_forward: cannot listen on 127.0.0.1:{listen_port}: {e}", file=sys.stderr)
        return 73
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
