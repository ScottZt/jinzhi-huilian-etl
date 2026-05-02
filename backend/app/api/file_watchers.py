from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.core.file_watcher import get_file_watcher
from app.persistence import sqlite_repo

router = APIRouter()
file_watcher = get_file_watcher()


class StartWatcher(BaseModel):
    connection_id: str


@router.get("/")
async def list_watchers():
    return file_watcher.list_watchers()


@router.post("/start")
async def start_watcher(body: StartWatcher):
    try:
        result = file_watcher.start_watcher(body.connection_id)
        return {"success": True, "message": result}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/{connection_id}/stop")
async def stop_watcher(connection_id: str):
    result = file_watcher.stop_watcher(connection_id)
    return {"message": result}


@router.post("/stop-all")
async def stop_all_watchers():
    file_watcher.stop_all()
    return {"message": "All watchers stopped"}
