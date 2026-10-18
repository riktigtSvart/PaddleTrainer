from hashlib import sha256
from pathlib import Path


def sha256_file(
    path: str | Path,
    *,
    chunk_size: int = 1024 * 1024,
) -> str:
    path = Path(path)

    digest = sha256()

    with path.open("rb") as stream:
        while True:
            chunk = stream.read(
                chunk_size
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()