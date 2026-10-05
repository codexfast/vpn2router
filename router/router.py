import asyncio
import base64
import os
import random
import re

LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8888"))
HTTP_UPSTREAMS = [s.strip() for s in os.getenv("HTTP_UPSTREAMS", "").split(",") if s.strip()]
DEBUG = os.getenv("ROUTER_DEBUG", "off").lower() == "on"


def load_users():
    users = {}
    for pair in os.getenv("ROUTER_USERS", "").split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        u, p = pair.split(":", 1)
        users[u.strip()] = p.strip()
    return users


USERS = load_users()
SUFFIX_RE = re.compile(r"^(.*?)[-#_](\d+)$")
ROTATE_RE = re.compile(r"^(.*?)[-#_](rotate|rodizio|livre|free)$", re.IGNORECASE)
ACTIVE = [0] * len(HTTP_UPSTREAMS)


def log(*a):
    if DEBUG:
        print(*a, flush=True)


def pick_upstream(username, n):
    m = ROTATE_RE.match(username)
    if m:
        return m.group(1), "rotate"
    m = SUFFIX_RE.match(username)
    if m:
        return m.group(1), (int(m.group(2)) - 1) % n
    return username, random.randrange(n)


NO_FREE = -1


def check_auth(username, password):
    n = len(HTTP_UPSTREAMS)
    if n == 0:
        return None, None
    base, slot = pick_upstream(username, n)
    if USERS.get(base) != password:
        return None, None
    if slot == "rotate":
        free = [i for i, a in enumerate(ACTIVE) if a <= 0]
        if not free:
            return base, NO_FREE
        pos = random.choice(free)
        ACTIVE[pos] += 1
        return base, pos
    ACTIVE[slot % n] += 1
    return base, slot % n


async def relay(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data:
                break
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


async def handle_http(reader, writer, first):
    data = first
    while b"\r\n\r\n" not in data:
        if len(data) > 65536:
            writer.close()
            return
        chunk = await reader.read(65536)
        if not chunk:
            break
        data += chunk
    try:
        head, _, _ = data.partition(b"\r\n\r\n")
        lines = head.decode("latin1").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        auth = headers.get("proxy-authorization", "")
        if not auth.lower().startswith("basic "):
            writer.write(b'HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic realm="vpn-router"\r\nContent-Length: 0\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        username, _, password = base64.b64decode(auth[6:]).decode("latin1").partition(":")
        base, pos = check_auth(username, password)
        if base is None:
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        if pos == NO_FREE:
            writer.write(b"HTTP/1.1 503 No free slots\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        uh, _, up = HTTP_UPSTREAMS[pos].partition(":")
        log(f"{username} -> {uh}:{up} {method} {target} (ativos={ACTIVE})")
        try:
            ur, uw = await asyncio.open_connection(uh, int(up))
        except Exception:
            ACTIVE[pos] = max(0, ACTIVE[pos] - 1)
            raise
        try:
            if method.upper() == "CONNECT":
                uw.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                await uw.drain()
                resp = b""
                while b"\r\n\r\n" not in resp:
                    chunk = await ur.read(65536)
                    if not chunk:
                        break
                    resp += chunk
                if b" 200 " not in resp.split(b"\r\n", 1)[0]:
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    writer.close()
                    uw.close()
                    return
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                uw.write(data)
                await uw.drain()
            await asyncio.gather(relay(reader, uw), relay(ur, writer))
        finally:
            ACTIVE[pos] = max(0, ACTIVE[pos] - 1)
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def handle_client(reader, writer):
    try:
        first = await reader.read(4096)
        if not first:
            writer.close()
            return
        if first[0] == 0x05:
            writer.write(b"\x05\xff")
            await writer.drain()
            writer.close()
            return
        await handle_http(reader, writer, first)
    except Exception:
        try:
            writer.close()
        except Exception:
            pass


async def main():
    print(f"router na porta {LISTEN_PORT} com {len(HTTP_UPSTREAMS)} backends, {len(USERS)} usuarios base", flush=True)
    server = await asyncio.start_server(handle_client, "0.0.0.0", LISTEN_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
