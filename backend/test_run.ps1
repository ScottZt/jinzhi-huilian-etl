$proc = Start-Process "D:\02.kdcz\quantsync-etl\backend\dist\QuantSyncETL.exe" -PassThru
Write-Host "PID: $($proc.Id) - Process started"
Write-Host "Waiting 30 seconds for full startup..."
for ($i = 5; $i -le 30; $i += 5) {
    Start-Sleep 5
    if ($proc.HasExited) {
        Write-Host "Process exited at ${i}s with code: $($proc.ExitCode)"
        break
    }
    Write-Host "Still running at ${i}s"
}
if (-not $proc.HasExited) {
    Write-Host "Process still running after 30s - killing now"
    $proc.Kill()
}
