"""Run SongMirror behind one Uvicorn server on IPv4 and IPv6."""

import asyncio
import os
import socket
import sys

import uvicorn


os.chdir("/app")
sys.path.insert(0, "/app")


def listener(family: int, address: str) -> socket.socket:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    sock.bind((address, 8080))
    sock.listen(2048)
    sock.setblocking(False)
    return sock


async def main() -> None:
    sockets = [
        listener(socket.AF_INET, "0.0.0.0"),
        listener(socket.AF_INET6, "::"),
    ]
    server = uvicorn.Server(uvicorn.Config("songmirror.web:app", log_level="info"))
    await server.serve(sockets=sockets)


if __name__ == "__main__":
    asyncio.run(main())
