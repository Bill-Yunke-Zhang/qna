from fastapi import UploadFile

from .exceptions import PayloadTooLargeError

# CSV rosters/staff lists are at most a few thousand short rows — a few KB
# to a couple hundred KB in the real worst case. This cap exists purely to
# bound memory use against an oversized or malicious upload; it is not
# meant to be a tight fit against expected file sizes.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
_CHUNK_SIZE = 65536


async def read_upload_capped(
    file: UploadFile, max_bytes: int = MAX_UPLOAD_BYTES
) -> bytes:
    """
    Read an UploadFile's contents while enforcing a hard size cap, so a
    single oversized upload can't exhaust backend memory. Plain
    `await file.read()` reads the whole body regardless of size — Starlette
    doesn't enforce any limit itself, and a client-supplied Content-Length
    header can't be trusted either (chunked transfer-encoding omits it
    entirely), so the only reliable guard is capping the actual bytes read.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError(
                f"File exceeds the {max_bytes // 1024} KB upload limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)
