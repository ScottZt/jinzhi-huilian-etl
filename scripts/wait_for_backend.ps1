# Wait for backend to become ready, then open the browser.
# Invoked in background by start.bat so the browser only opens after the server is actually serving.
param(
    [string]$Url = "http://127.0.0.1:8080/",
    [int]$TimeoutSeconds = 120
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process $Url
            exit 0
        }
    } catch {
        # Backend not ready yet, keep waiting.
    }
}
Write-Warning "Backend did not respond within $TimeoutSeconds seconds, opening browser anyway..."
Start-Process $Url
exit 1
