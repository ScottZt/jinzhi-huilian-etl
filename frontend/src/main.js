const { app, BrowserWindow, Menu, Tray, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const http = require('http');
const net = require('net');
const log = require('electron-log');

log.transports.file.level = 'info';
log.transports.console.level = 'debug';

let mainWindow = null;
let backendProcess = null;
let isQuitting = false;
let tray = null;
let trayStatusTimer = null;
let backendRecoveryTimer = null;
let hasShownMinimizeTip = false;
// Track the actual backend port in use (may fallback from 8080 to 8081+).
let currentBackendPort = 8080;
// 记录后端启动状态，避免启动失败后窗口仅显示黑屏。
let backendReady = false;
let backendStartError = '';

const isDev = process.argv.includes('--dev');
// DevTools is opt-in now; pass --open-devtools when needed.
const shouldOpenDevTools = process.argv.includes('--open-devtools');

// Determine backend entry path
const backendPath = path.join(__dirname, '..', '..', 'backend');
// In production, the backend exe is bundled inside extraResources
const bundledBackendExe = process.platform === 'win32'
  ? path.join(process.resourcesPath, 'backend-server', 'backend-server.exe')
  : path.join(process.resourcesPath, 'backend-server', 'backend-server');
const PYTHON = process.platform === 'win32' ? 'python' : 'python3';

// Keep runtime DB/cache under project shared dir for stable dev behavior.
// In production, set in app.whenReady() before starting backend.
let backendDataDir = isDev ? path.resolve(backendPath, '..', 'shared') : '';
// Use project root logo as app/window icon source.
// In dev: project root logo.png. In production: resources path.
const projectLogoPath = isDev
  ? path.resolve(backendPath, '..', 'logo.png')
  : path.join(process.resourcesPath, 'logo.png');
const PORT_RANGE_START = 8080;
const PORT_RANGE_END = 8099;

function getPort() {
  return currentBackendPort;
}

function checkPortInUse(port, host = '127.0.0.1', timeoutMs = 400) {
  // Probe if a TCP port has a listener by attempting a short socket connect.
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let done = false;
    const finish = (result) => {
      if (done) return;
      done = true;
      socket.destroy();
      resolve(result);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, host);
  });
}

async function getOccupiedPorts(startPort = 8080, endPort = 8099) {
  // Scan a small port range and return all currently occupied ports.
  const occupied = [];
  for (let p = startPort; p <= endPort; p += 1) {
    // eslint-disable-next-line no-await-in-loop
    const used = await checkPortInUse(p);
    if (used) occupied.push(p);
  }
  return occupied;
}

async function findHealthyBackendPort(startPort = PORT_RANGE_START, endPort = PORT_RANGE_END) {
  // Reuse any healthy backend in range to avoid launching duplicate backend processes.
  for (let p = startPort; p <= endPort; p += 1) {
    // eslint-disable-next-line no-await-in-loop
    const healthy = await checkBackendHealth(p, 500);
    if (healthy) return p;
  }
  return null;
}

async function findFreePort(startPort = PORT_RANGE_START, endPort = PORT_RANGE_END) {
  // Pick the first available TCP port in range for backend startup fallback.
  for (let p = startPort; p <= endPort; p += 1) {
    // eslint-disable-next-line no-await-in-loop
    const inUse = await checkPortInUse(p, '127.0.0.1', 300);
    if (!inUse) return p;
  }
  return null;
}

async function showPortUsageDialog() {
  // Show a quick diagnostic dialog with occupied ports in the default backend range.
  const occupied = await getOccupiedPorts(PORT_RANGE_START, PORT_RANGE_END);
  const detail = occupied.length
    ? `已占用端口: ${occupied.join(', ')}`
    : `${PORT_RANGE_START}-${PORT_RANGE_END} 范围内暂无端口占用。`;
  await dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: '端口占用信息',
    message: '当前端口占用扫描结果',
    detail,
  });
}

function checkBackendHealth(port, timeoutMs = 2000) {
  // Probe backend /health endpoint to verify the service is actually ready.
  return new Promise((resolve) => {
    const req = http.get(
      {
        hostname: '127.0.0.1',
        port,
        path: '/health',
        timeout: timeoutMs,
      },
      (res) => {
        // Any 2xx response from /health means backend is alive.
        resolve(res.statusCode >= 200 && res.statusCode < 300);
      },
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function waitForBackendHealth(port, totalTimeoutMs = 15000, intervalMs = 500) {
  // Poll /health until timeout to avoid false-positive startup state.
  const startedAt = Date.now();
  while (Date.now() - startedAt < totalTimeoutMs) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await checkBackendHealth(port, intervalMs);
    if (ok) return true;
    // eslint-disable-next-line no-await-in-loop
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return false;
}

function getBackendStartupTimeoutMs() {
  // 生产环境机器差异更大（杀软扫描/磁盘慢），给更长启动缓冲，避免误判失败。
  return isDev ? 15000 : 45000;
}

function startBackend() {
  return new Promise((resolve, reject) => {
    log.info(`[QuantSync ETL] Starting backend in port range ${PORT_RANGE_START}-${PORT_RANGE_END}...`);

    let settled = false;
    const finishResolve = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    const finishReject = (err) => {
      if (!settled) {
        settled = true;
        reject(err);
      }
    };

    const launchBackendProcess = (port) => {
      // Persist selected backend port so the UI always targets the right endpoint.
      currentBackendPort = port;

      let backendCmd, backendArgs, envOpts;

      if (isDev) {
        // Dev mode: use system Python
        backendCmd = PYTHON;
        backendArgs = ['-c', `
import sys
sys.path.insert(0, r'${backendPath}')
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=${port})
`];
        envOpts = {
          ...process.env,
          PYTHONPATH: backendPath,
          JINZHIHUILIAN_DATA_DIR: backendDataDir,
          JINZHIHUI_DATA_DIR: backendDataDir,
        };
      } else {
        // Production: use bundled PyInstaller exe
        if (!fs.existsSync(bundledBackendExe)) {
          log.error(`[QuantSync ETL] Backend exe not found: ${bundledBackendExe}`);
          finishReject(new Error(`Backend executable not found at ${bundledBackendExe}`));
          return;
        }
        backendCmd = bundledBackendExe;
        backendArgs = [];
        envOpts = {
          ...process.env,
          JINZHIHUILIAN_DATA_DIR: backendDataDir,
          JINZHIHUI_DATA_DIR: backendDataDir,
          JINZHIHUILIAN_PORT: String(port),
        };
      }

      backendProcess = spawn(backendCmd, backendArgs, {
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: false,
        shell: false,
        env: envOpts,
        cwd: path.dirname(backendCmd),
      });

      // Log the backend spawn event
      if (isDev) {
        log.info(`[Backend] Using system Python on port ${port}`);
      } else {
        log.info(`[Backend] Using bundled exe at ${bundledBackendExe} on port ${port}`);
      }

      backendProcess.stdout.on('data', (data) => {
        const msg = data.toString();
        log.info(`[Backend] ${msg.trim()}`);
        // Keep logs only; readiness is decided by health polling below.
      });

      backendProcess.stderr.on('data', (data) => {
        const msg = data.toString().trim();
        log.warn(`[Backend ERR] ${msg}`);
        // Port bind errors should fail fast to avoid waiting full timeout.
        if (msg.includes('WinError 10048') || msg.includes('Errno 10048')) {
          finishReject(new Error(`Backend port ${port} is already in use`));
        }
      });

      backendProcess.on('error', (err) => {
        log.error(`[Backend] Failed to start: ${err.message}`);
        finishReject(err);
      });

      backendProcess.on('exit', (code) => {
        log.info(`[Backend] Exited with code ${code}`);
        // If process exits before startup completes, report startup failure.
        if (!settled && code !== 0) {
          finishReject(new Error(`Backend exited before ready (code=${code})`));
        }
        if (!isQuitting) {
          log.warn('[Backend] Backend stopped unexpectedly');
        }
      });

      // Actively poll selected backend health. On timeout, do one more range probe before failing.
      waitForBackendHealth(port, getBackendStartupTimeoutMs(), 500).then(async (ok) => {
        if (ok) {
          finishResolve();
        } else {
          // 超时后再扫描一次端口范围，兜底“后端晚启动/端口回退”的场景，降低假失败率。
          const healthyPort = await findHealthyBackendPort(PORT_RANGE_START, PORT_RANGE_END);
          if (healthyPort !== null) {
            currentBackendPort = healthyPort;
            log.info(`[QuantSync ETL] Backend became healthy on port ${healthyPort} after timeout window`);
            finishResolve();
            return;
          }
          finishReject(new Error(`Backend health check timeout on port ${port}`));
        }
      }).catch((err) => finishReject(err));
    };

    // Reuse any healthy backend first to avoid duplicate backend instances.
    findHealthyBackendPort(PORT_RANGE_START, PORT_RANGE_END).then((healthyPort) => {
      if (healthyPort !== null) {
        currentBackendPort = healthyPort;
        log.info(`[QuantSync ETL] Existing backend detected on port ${healthyPort}, reusing current service`);
        finishResolve();
        return;
      }
      // If no healthy backend exists, pick a free port and launch exactly one backend.
      findFreePort(PORT_RANGE_START, PORT_RANGE_END).then((freePort) => {
        if (freePort === null) {
          finishReject(new Error(`No free port in range ${PORT_RANGE_START}-${PORT_RANGE_END}`));
          return;
        }
        log.info(`[QuantSync ETL] Launching backend on free port ${freePort}`);
        launchBackendProcess(freePort);
      }).catch((err) => finishReject(err));
    }).catch(() => {
      // Probe failed; fallback to free-port launch flow.
      findFreePort(PORT_RANGE_START, PORT_RANGE_END).then((freePort) => {
        if (freePort === null) {
          finishReject(new Error(`No free port in range ${PORT_RANGE_START}-${PORT_RANGE_END}`));
          return;
        }
        launchBackendProcess(freePort);
      }).catch((err) => finishReject(err));
    });
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

function clearBackendRecoveryTimer() {
  // 统一清理诊断页恢复探测定时器，避免重复注册。
  if (backendRecoveryTimer) {
    clearInterval(backendRecoveryTimer);
    backendRecoveryTimer = null;
  }
}

function startBackendRecoveryProbe() {
  // 启动失败后持续探测后端，一旦健康则自动切回主界面，减少用户手工刷新步骤。
  clearBackendRecoveryTimer();
  backendRecoveryTimer = setInterval(async () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (backendReady) {
      clearBackendRecoveryTimer();
      return;
    }
    try {
      const healthyPort = await findHealthyBackendPort(PORT_RANGE_START, PORT_RANGE_END);
      if (healthyPort !== null) {
        currentBackendPort = healthyPort;
        backendReady = true;
        backendStartError = '';
        clearBackendRecoveryTimer();
        log.info(`[QuantSync ETL] Recovery probe detected healthy backend on port ${healthyPort}, reloading window`);
        await mainWindow.loadURL(`http://localhost:${getPort()}`);
      }
    } catch (err) {
      // 恢复探测仅做兜底，不影响主流程；异常写日志后继续下一轮探测。
      log.warn(`[QuantSync ETL] Recovery probe failed: ${err.message}`);
    }
  }, 2000);
}

async function getBackendRuntimeStatus() {
  // 统一收集托盘和菜单需要展示的后端状态信息。
  const port = getPort();
  const healthy = await checkBackendHealth(port, 1000);
  return {
    port,
    healthy,
    pid: backendProcess ? backendProcess.pid : null,
    source: backendProcess ? '内置后端进程' : '复用外部后端服务',
  };
}

function showWindowFromTray() {
  // 通过托盘恢复主窗口，保持单一入口行为一致。
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.show();
  mainWindow.focus();
}

async function showBackendStatusDialog() {
  // 通过弹窗展示后端运行态，便于用户在托盘中做状态管理。
  const status = await getBackendRuntimeStatus();
  const summary = status.healthy ? '运行中' : '不可用';
  const pidText = status.pid ? `PID: ${status.pid}` : 'PID: 非本进程托管';
  await dialog.showMessageBox(mainWindow, {
    type: status.healthy ? 'info' : 'warning',
    title: '后端状态',
    message: `后端当前状态：${summary}`,
    detail: `地址: http://127.0.0.1:${status.port}\n来源: ${status.source}\n${pidText}`,
  });
}

async function restartBackendFromTray() {
  // 托盘触发重启时复用现有重启流程，并在完成后刷新主窗口目标地址。
  try {
    stopBackend();
    await startBackend();
    if (mainWindow) {
      await mainWindow.loadURL(`http://localhost:${getPort()}`);
    }
    await refreshTrayMenu();
    await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: '后端重启',
      message: '后端服务已重启',
      detail: `当前地址: http://127.0.0.1:${getPort()}`,
    });
  } catch (error) {
    log.error(`[Tray] Restart backend failed: ${error.message}`);
    await dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: '后端重启失败',
      message: '无法完成后端重启',
      detail: error.message,
    });
  }
}

async function buildTrayMenuTemplate() {
  // 每次动态构建托盘菜单，确保状态项反映最新健康检查结果。
  const status = await getBackendRuntimeStatus();
  const statusLabel = status.healthy
    ? `后端状态: 运行中 (:${status.port})`
    : `后端状态: 异常 (:${status.port})`;
  return [
    { label: '打开主界面', click: () => showWindowFromTray() },
    { label: statusLabel, enabled: false },
    { type: 'separator' },
    { label: '查看后端状态', click: () => { showBackendStatusDialog(); } },
    { label: '重启后端服务', click: () => { restartBackendFromTray(); } },
    { label: '打开日志文件夹', click: () => { shell.showItemInFolder(log.transports.file.getFile().path); } },
    { type: 'separator' },
    {
      label: '退出程序',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ];
}

async function refreshTrayMenu() {
  // 托盘菜单支持按需刷新，持续提供可观测状态。
  if (!tray) return;
  const template = await buildTrayMenuTemplate();
  const menu = Menu.buildFromTemplate(template);
  tray.setContextMenu(menu);
}

function notifyMinimizeToTrayOnce() {
  // 首次隐藏到托盘时给出提示，避免用户误以为应用已经退出。
  if (hasShownMinimizeTip || !tray) return;
  hasShownMinimizeTip = true;
  if (process.platform === 'win32' && typeof tray.displayBalloon === 'function') {
    tray.displayBalloon({
      iconType: 'info',
      title: 'QuantSync ETL',
      content: '程序已最小化到托盘，服务仍在后台运行。',
    });
  }
}

function createTray() {
  // 创建常驻托盘图标，用于窗口恢复、状态查看和退出管理。
  if (tray) return;
  tray = new Tray(projectLogoPath);
  tray.setToolTip('QuantSync ETL');
  tray.on('double-click', () => {
    showWindowFromTray();
  });
  tray.on('click', () => {
    showWindowFromTray();
  });
  tray.on('right-click', () => {
    refreshTrayMenu();
  });
  refreshTrayMenu();
  // 定时刷新菜单中的状态项，确保托盘长期驻留时状态可见。
  trayStatusTimer = setInterval(() => {
    refreshTrayMenu();
  }, 15000);
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
    // Use root logo for window/taskbar icon on Windows/Linux.
    icon: projectLogoPath,
  });

  const url = `http://localhost:${getPort()}`;

  // 启动失败时先渲染诊断页，避免用户只看到黑屏。
  if (backendReady) {
    clearBackendRecoveryTimer();
    mainWindow.loadURL(url);
  } else {
    const safeErr = (backendStartError || '后端启动失败').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const fallbackHtml = `
      <html><head><meta charset="UTF-8"><title>QuantSync ETL 启动诊断</title></head>
      <body style="margin:0;font-family:'Microsoft YaHei',sans-serif;background:#0f1117;color:#d1d5db">
        <div style="max-width:860px;margin:48px auto;padding:24px;background:#111827;border:1px solid #374151;border-radius:12px">
          <h2 style="margin:0 0 12px 0;color:#f9fafb">启动失败诊断</h2>
          <p style="margin:0 0 10px 0;line-height:1.8">后端未就绪，主界面暂不可用。请先查看日志定位问题。</p>
          <div style="margin:12px 0;padding:12px;background:#1f2937;border-radius:8px;font-size:12px;line-height:1.7">
            <div>目标地址：${url}</div>
            <div>错误信息：${safeErr}</div>
            <div>建议：菜单「帮助 -> 重启后端服务」后，再「视图 -> 重新加载」</div>
          </div>
        </div>
      </body></html>`;
    mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(fallbackHtml)}`);
    startBackendRecoveryProbe();
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    log.info('[QuantSync ETL] Window shown');
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
      notifyMinimizeToTrayOnce();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 页面加载失败时记录日志并显示可操作错误页，避免纯黑屏。
  mainWindow.webContents.on('did-fail-load', (_event, code, desc, validatedURL) => {
    log.error(`[Renderer] did-fail-load code=${code} desc=${desc} url=${validatedURL}`);
    const safeUrl = String(validatedURL || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const safeDesc = String(desc || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const html = `
      <html><head><meta charset="UTF-8"><title>页面加载失败</title></head>
      <body style="margin:0;font-family:'Microsoft YaHei',sans-serif;background:#0f1117;color:#d1d5db">
        <div style="max-width:860px;margin:48px auto;padding:24px;background:#111827;border:1px solid #374151;border-radius:12px">
          <h2 style="margin:0 0 12px 0;color:#f9fafb">页面加载失败</h2>
          <p style="line-height:1.8">无法连接到后端服务，请先在菜单中重启后端服务。</p>
          <div style="margin:12px 0;padding:12px;background:#1f2937;border-radius:8px;font-size:12px;line-height:1.7">
            <div>URL：${safeUrl}</div>
            <div>错误：${safeDesc} (code=${code})</div>
          </div>
        </div>
      </body></html>`;
    mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
  });

  // Do not auto-open DevTools by default to avoid disturbing normal usage.
  if (isDev && shouldOpenDevTools) {
    mainWindow.webContents.openDevTools();
  }
}

function createMenu() {
  // Use explicit Chinese labels for menu items to avoid English defaults.
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
        { label: '退出', accelerator: 'CmdOrCtrl+Q', click: () => { isQuitting = true; app.quit(); } },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { label: '撤销', role: 'undo' }, { label: '重做', role: 'redo' },
        { type: 'separator' },
        { label: '剪切', role: 'cut' }, { label: '复制', role: 'copy' }, { label: '粘贴', role: 'paste' },
        { label: '全选', role: 'selectAll' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { label: '重新加载', role: 'reload' }, { label: '强制重新加载', role: 'forceReload' },
        { type: 'separator' },
        { label: '实际大小', role: 'resetZoom' }, { label: '放大', role: 'zoomIn' }, { label: '缩小', role: 'zoomOut' },
        { type: 'separator' },
        { label: '切换全屏', role: 'togglefullscreen' },
      ],
    },
    {
      label: '窗口',
      submenu: [
        { label: '最小化', role: 'minimize' },
        { label: '缩放', role: 'zoom' },
        { label: '关闭窗口', role: 'close' },
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
        {
          label: '查看端口占用',
          click: async () => {
            await showPortUsageDialog();
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

ipcMain.handle('select-directory', async () => {
  // 打开原生目录选择对话框，跨平台返回用户选择的本地目录路径。
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择本地数据目录',
    properties: ['openDirectory', 'createDirectory'],
  });
  // 用户取消时返回空字符串，前端可据此保持原值不变。
  return result.canceled ? '' : (result.filePaths[0] || '');
});

// App lifecycle
// Enforce single app instance to avoid repeated Electron launches and duplicate backend startups.
const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
}

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

app.whenReady().then(async () => {
  log.info('[QuantSync ETL] Starting...');

  // In production, use AppData dir for runtime data
  if (!isDev && process.env.APPDATA) {
    backendDataDir = path.join(process.env.APPDATA, 'QuantSyncETL', 'data');
    try { require('fs').mkdirSync(backendDataDir, { recursive: true }); } catch(e) { /* use fallback */ }
  }

  createMenu();
  createTray();

  try {
    await startBackend();
    log.info('[QuantSync ETL] Backend started');
    backendReady = true;
    backendStartError = '';
    await refreshTrayMenu();
  } catch (e) {
    log.error(`[QuantSync ETL] Backend failed: ${e.message}`);
    backendReady = false;
    backendStartError = e.message;
    await refreshTrayMenu();
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
  // 真正退出时释放托盘资源并停止后端进程。
  isQuitting = true;
  clearBackendRecoveryTimer();
  if (trayStatusTimer) {
    clearInterval(trayStatusTimer);
    trayStatusTimer = null;
  }
  if (tray) {
    tray.destroy();
    tray = null;
  }
  stopBackend();
});

process.on('uncaughtException', (err) => {
  log.error(`[Uncaught Exception] ${err.message}\n${err.stack}`);
});

process.on('unhandledRejection', (reason) => {
  log.error(`[Unhandled Rejection] ${reason}`);
});
