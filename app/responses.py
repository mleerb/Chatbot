from urllib.parse import quote

from fastapi import Response


def download_response(filename: str, data: bytes) -> Response:
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"download\"; filename*=UTF-8''{quote(filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


def image_response(filename: str, data: bytes) -> Response:
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Content-Disposition": f"inline; filename=\"image.png\"; filename*=UTF-8''{quote(filename, safe='')}",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )
