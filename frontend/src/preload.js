const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  onBackendRestart: (callback) => {
    ipcRenderer.on('backend-restarted', callback);
    return () => ipcRenderer.removeListener('backend-restarted', callback);
  },
});
