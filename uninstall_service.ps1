# Desinstala el monitor de Ripley del arranque automatico
$TaskName = "RipleyPriceMonitor"

Stop-ScheduledTask  -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Monitor desinstalado del arranque automatico." -ForegroundColor Yellow
