from urllib.parse import unquote

from starlette.responses import FileResponse, Response
from starlette.routing import Route

from download_service import _safe_download_path, find_entry_by_stored_name


async def serve_download(request) -> Response:
    stored_name = unquote(request.path_params["stored_name"])
    file_path = _safe_download_path(stored_name)
    if file_path is None or not file_path.is_file():
        return Response(status_code=404)

    entry = find_entry_by_stored_name(stored_name)
    if entry is None:
        return Response(status_code=404)

    filename = entry.get("filename", stored_name)
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=filename,
    )


def build_download_routes() -> list[Route]:
    return [
        Route(
            "/api/download/{stored_name}",
            serve_download,
            methods=["GET"],
        ),
    ]
