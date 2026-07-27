import aiohttp

_http_session: aiohttp.ClientSession | None = None


async def create_http_session():
    global _http_session

    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=2,
                connect=1,
                sock_read=2,
            )
        )


def get_http_session() -> aiohttp.ClientSession:
    if _http_session is None:
        raise RuntimeError("HTTP session hali yaratilmagan")
    return _http_session


async def close_http_session():
    global _http_session

    if _http_session and not _http_session.closed:
        await _http_session.close()