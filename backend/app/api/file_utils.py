from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Tuple
import threading
import os

router = APIRouter()


class FileDialogRequest(BaseModel):
    title: str = "Select File"
    filetypes: Optional[List[Tuple[str, str]]] = None
    defaultextension: str = ""
    initialdir: str = ""


class FileDialogResponse(BaseModel):
    path: Optional[str] = None
    cancelled: bool = True


@router.post("/dialog", response_model=FileDialogResponse)
async def open_file_dialog(req: FileDialogRequest):
    """Open a native file picker dialog and return the selected file path.

    Uses tkinter's filedialog, which works cross-platform.
    The dialog runs on a dedicated thread with a hidden root window.
    """
    import tkinter as tk
    from tkinter import filedialog

    result = {"path": None}

    def _show_dialog():
        root = tk.Tk()
        root.withdraw()
        # 置顶确保对话框不被浏览器遮挡
        root.attributes("-topmost", True)

        filetypes = req.filetypes or [("All Files", "*.*")]
        path = filedialog.askopenfilename(
            title=req.title,
            filetypes=filetypes,
            defaultextension=req.defaultextension,
            initialdir=req.initialdir or os.path.expanduser("~"),
        )
        result["path"] = path if path else None
        root.destroy()

    t = threading.Thread(target=_show_dialog, daemon=True)
    t.start()
    t.join(timeout=120)

    if result["path"]:
        return FileDialogResponse(path=result["path"], cancelled=False)
    return FileDialogResponse(path=None, cancelled=True)
