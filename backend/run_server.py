"""Server entry point - used by start.bat"""
import sys
sys.path.insert(0, '.')
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8080)
