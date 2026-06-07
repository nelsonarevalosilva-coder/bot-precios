# Instala el monitor de Ripley como tarea programada de Windows
# Se inicia automaticamente al encender el PC (sin ventana visible)
# Los logs se guardan en: ripley-monitor\monitor.log

$TaskName = "RipleyPriceMonitor"
$PythonW = "C:\Users\narev\AppData\Local\Programs\Python\Python312\pythonw.exe"
$Script  = "c:\Users\narev\Desktop\OPEN\ripley-monitor\catalog_monitor.py"
$WorkDir = "c:\Users\narev\Desktop\OPEN\ripley-monitor"

# Eliminar tarea previa si existe
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# Crear la accion
$Action = New-ScheduledTaskAction `
    -Execute $PythonW `
    -Argument $Script `
    -WorkingDirectory $WorkDir

# Disparador: al iniciar sesion del usuario actual
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Configuracion: reiniciar si falla, ejecutar aunque no haya red inmediata
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

# Registrar la tarea
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host ""
Write-Host "=== Monitor de Ripley instalado como servicio ===" -ForegroundColor Green
Write-Host ""
Write-Host "Tarea: $TaskName" -ForegroundColor Cyan
Write-Host "Se inicia automaticamente al encender el PC"
Write-Host "Corre en segundo plano (sin ventana)"
Write-Host "Logs en: $WorkDir\monitor.log"
Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor Yellow
Write-Host "  Iniciar ahora:   Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "  Detener:         Stop-ScheduledTask  -TaskName '$TaskName'"
Write-Host "  Ver estado:      Get-ScheduledTask   -TaskName '$TaskName'"
Write-Host "  Desinstalar:     .\uninstall_service.ps1"
Write-Host ""

# Iniciar inmediatamente
Write-Host "Iniciando el monitor ahora..." -ForegroundColor Yellow
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2
$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Estado: $state" -ForegroundColor $(if ($state -eq 'Running') { 'Green' } else { 'Red' })
