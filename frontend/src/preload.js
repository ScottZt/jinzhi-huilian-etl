const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  // 打开系统目录选择器，供前端选择通达信本地目录。
  selectDirectory: () => ipcRenderer.invoke('select-directory'),

  onBackendRestart: (callback) => {
    ipcRenderer.on('backend-restarted', callback);
    return () => ipcRenderer.removeListener('backend-restarted', callback);
  },
});
