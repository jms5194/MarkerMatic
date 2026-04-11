Write-Host "Launching MarkerMatic"
try {
    $Process = Start-Process -FilePath $args[0] -ArgumentList "--check-health" -PassThru -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 30
    Stop-Process -InputObject $Process -ErrorAction SilentlyContinue
}
catch {}
if ($Process.ExitCode -eq 0) {
    Write-Host "Health check completed successfully"
    exit 0
}
else {
    Write-Host "Health check failed with exit code $($Process.ExitCode)"
    exit 1
}