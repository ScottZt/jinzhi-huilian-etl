# QuantSync ETL - Electron Frontend

## Development

```bash
# Install dependencies
npm install

# Run in development mode (starts backend + opens Electron window)
npm run dev

# Or run Electron without auto-backend (backend must be started separately)
npm start
```

## Build

### Windows

```bash
npm install
npx electron-builder --win --x64
# Output: dist/QuantSync-ETL-Setup-1.0.0.exe
```

### macOS

```bash
npm install
npx electron-builder --mac
# Output: dist/QuantSync-ETL-1.0.0.dmg
```

### Both platforms

```bash
npm run build:all
```

## Notes

- The Electron main process automatically starts the Python FastAPI backend on port 8080
- The frontend is served by the FastAPI backend (no separate dev server needed)
- Build requires Python 3.9+ and Node.js 18+
- Windows build must be run in Git Bash, WSL, or similar Unix-like environment
