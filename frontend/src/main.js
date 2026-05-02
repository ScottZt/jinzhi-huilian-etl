const { app, BrowserWindow, Menu, Tray, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const log = require('electron-log');

log.transports.file.level = 'info';
log.transports.console.level = 'debug';

let mainWindow = null;
let backendProcess = null;
let isQuitting = false;

const isDev = process.argv.includes('--dev');

// Determine backend entry path
const backendPath = path.join(__dirname, '..', '..', 'backend');
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';

function getPort() {
  return 8080;
}

function startBackend() {
  return new Promise((resolve, reject) => {
    const port = getPort();
    log.info(`[QuantSync ETL] Starting backend on port ${port}...`);

    const args = ['-c', `import sys; sys.path.insert(0, '${backendPath.replace(/\\/g, '\\\\')}'); from app.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=${port})`];

    backendProcess = spawn(PYTHON, ['-c', `
import sys
sys.path.insert(0, r'${backendPath}')
from app.main import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=${port})
`], {
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: false,
      shell: false,
      env: { ...process.env, PYTHONPATH: backendPath },
    });

    backendProcess.stdout.on('data', (data) => {
      const msg = data.toString();
      log.info(`[Backend] ${msg.trim()}`);
      if (msg.includes('Uvicorn running') || msg.includes('Started server')) {
        resolve();
      }
    });

    backendProcess.stderr.on('data', (data) => {
      log.warn(`[Backend ERR] ${data.toString().trim()}`);
    });

    backendProcess.on('error', (err) => {
      log.error(`[Backend] Failed to start: ${err.message}`);
      reject(err);
    });

    backendProcess.on('exit', (code) => {
      log.info(`[Backend] Exited with code ${code}`);
      if (!isQuitting) {
        log.warn('[Backend] Backend stopped unexpectedly');
      }
    });

    // Timeout after 15 seconds
    setTimeout(() => {
      resolve();
    }, 15000);
  });
}

function stopBackend() {
  if (backendProcess) {
    log.info('[QuantSync ETL] Stopping backend...');
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', backendProcess.pid, '/f', '/t']);
    } else {
      backendProcess.kill('SIGTERM');
    }
    backendProcess = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0f1117',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    show: false,
    title: 'QuantSync ETL',
  });

  const url = isDev
    ? `http://localhost:${getPort()}`
    : `http://localhost:${getPort()}`;

  mainWindow.loadURL(url);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    log.info('[QuantSync ETL] Window shown');
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  if (isDev) {
    mainWindow.webContents.openDevTools();
  }
}

function createMenu() {
  const template = [
    {
      label: 'QuantSync ETL',
      submenu: [
        { label: '关于', click: () => {
          dialog.showMessageBox(mainWindow, {
            type: 'info',
            title: '关于 QuantSync ETL',
            message: 'QuantSync ETL v1.0.0',
            detail: '量化数据同步工具\n支持多种数据库和文件格式的ETL处理',
          });
        }},
        { type: 'separator' },
        { label: 'Quit', accelerator: 'CmdOrCtrl+Q', click: () => { isQuitting = true; app.quit(); } },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { role: 'undo' }, { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' }, { role: 'copy' }, { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload' }, { role: 'forceReload' },
        { type: 'separator' },
        { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: '窗口',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        { role: 'close' },
      ],
    },
    {
      label: '帮助',
      submenu: [
        {
          label: '打开日志文件夹',
          click: () => { shell.showItemInFolder(log.transports.file.getFile().path); },
        },
        {
          label: '重启后端服务',
          click: async () => {
            stopBackend();
            await startBackend();
            if (mainWindow) mainWindow.loadURL(`http://localhost:${getPort()}`);
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// IPC handlers
ipcMain.handle('get-backend-status', () => {
  return backendProcess !== null;
});

ipcMain.handle('restart-backend', async () => {
  stopBackend();
  await startBackend();
  return true;
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

// App lifecycle
app.whenReady().then(async () => {
  log.info('[QuantSync ETL] Starting...');
  createMenu();

  try {
    await startBackend();
    log.info('[QuantSync ETL] Backend started');
  } catch (e) {
    log.error(`[QuantSync ETL] Backend failed: ${e.message}`);
  }

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    isQuitting = true;
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

process.on('uncaughtException', (err) => {
  log.error(`[Uncaught Exception] ${err.message}\n${err.stack}`);
});

process.on('unhandledRejection', (reason) => {
  log.error(`[Unhandled Rejection] ${reason}`);
});
