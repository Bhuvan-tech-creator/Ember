import threading
import uuid

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ember_core import analyze
from geomap import preview_map_for_address, pixel_to_lat_lon


app = FastAPI(title="Ember")

JOBS = {}
MAP_PREVIEWS = {}


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/prepare-map")
async def prepare_map(address: str = Form(default="")):
    address = address.strip()

    if not address:
        return JSONResponse(
            {"error": "Enter a full US address before loading the aerial map."},
            status_code=400,
        )

    try:
        preview = preview_map_for_address(address)

        if not preview:
            return JSONResponse(
                {
                    "error": (
                        "Could not locate this address with Census or retrieve aerial imagery. "
                        "Check the street, city, state, and ZIP."
                    )
                },
                status_code=400,
            )

        map_id = uuid.uuid4().hex[:16]
        MAP_PREVIEWS[map_id] = preview

        return {
            "map_id": map_id,
            "image_b64": preview["image_b64"],
            "width": preview["width"],
            "height": preview["height"],
            "message": preview["message"],
        }

    except Exception as error:
        return JSONResponse(
            {"error": f"Could not prepare aerial map: {error}"},
            status_code=400,
        )


@app.post("/api/confirm-target")
async def confirm_target(
    map_id: str = Form(...),
    pixel_x: float = Form(...),
    pixel_y: float = Form(...),
):
    preview = MAP_PREVIEWS.get(map_id)

    if not preview:
        return JSONResponse(
            {
                "error": (
                    "The aerial map session expired. Reload the map and click "
                    "your roof again."
                )
            },
            status_code=400,
        )

    if pixel_x < 0 or pixel_y < 0:
        return JSONResponse(
            {"error": "Invalid map click coordinates."},
            status_code=400,
        )

    if pixel_x > preview["width"] or pixel_y > preview["height"]:
        return JSONResponse(
            {"error": "Your click was outside the aerial image."},
            status_code=400,
        )

    latitude, longitude = pixel_to_lat_lon(preview, pixel_x, pixel_y)

    return {
        "target_lat": latitude,
        "target_lon": longitude,
        "message": "Roof target confirmed from your map click.",
    }


@app.post("/api/start")
async def api_start(
    video: UploadFile = File(...),
    address: str = Form(default=""),
    windows: str = Form(default="Not sure"),
    firewise: str = Form(default="Not sure"),
    target_lat: str = Form(default=""),
    target_lon: str = Form(default=""),
):
    video_bytes = await video.read()
    job_id = uuid.uuid4().hex[:12]

    target = None

    if target_lat.strip() and target_lon.strip():
        try:
            target = (float(target_lat), float(target_lon))
        except ValueError:
            return JSONResponse(
                {"error": "Invalid selected roof coordinates."},
                status_code=400,
            )

    JOBS[job_id] = {
        "pct": 4,
        "msg": "Queued…",
        "status": "running",
        "result": None,
    }

    def work():
        def progress(percent, message):
            JOBS[job_id].update(
                {
                    "pct": int(percent),
                    "msg": message,
                }
            )

        try:
            result = analyze(
                video_bytes=video_bytes,
                address=address,
                manual={
                    "windows": windows,
                    "firewise": firewise,
                },
                selected_target=target,
                on_progress=progress,
            )

            JOBS[job_id].update(
                {
                    "status": "done",
                    "pct": 100,
                    "msg": "Complete ✅",
                    "result": result,
                }
            )

        except Exception as error:
            JOBS[job_id].update(
                {
                    "status": "error",
                    "msg": str(error),
                }
            )

    threading.Thread(target=work, daemon=True).start()

    return {"job_id": job_id}


@app.get("/api/progress")
def api_progress(job: str):
    job_data = JOBS.get(job)

    if not job_data:
        return JSONResponse(
            {
                "status": "error",
                "msg": "Unknown analysis job.",
            },
            status_code=404,
        )

    return {
        "pct": job_data["pct"],
        "msg": job_data["msg"],
        "status": job_data["status"],
    }


@app.get("/api/result")
def api_result(job: str):
    job_data = JOBS.get(job)

    if not job_data:
        return JSONResponse(
            {"error": "Unknown analysis job."},
            status_code=404,
        )

    if job_data["status"] != "done":
        return JSONResponse(
            {"error": "Analysis result is not ready yet."},
            status_code=202,
        )

    return job_data["result"]


app.mount("/static", StaticFiles(directory="static"), name="static")