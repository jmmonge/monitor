# Script generado el 04/02/2026 11:22:09
Import-Module Veeam.Backup.PowerShell -DisableNameChecking -ErrorAction Stop

# Conexión
Disconnect-VBRServer -ErrorAction SilentlyContinue | Out-Null
Connect-VBRServer -Server "192.168.20.254" -ErrorAction Stop

# 1. Obtener todos los trabajos (incluyendo Backup Copy)
$allJobs = Get-VBRJob -WarningAction SilentlyContinue
$agentJobs = Get-VBRComputerBackupJob
$allJobs = @($allJobs; $agentJobs)

# --- OPTIMIZACIÓN CLAVE: Cargar sesiones una sola vez ---
Write-Host "Cargando historial de sesiones (esto ahorrará mucho tiempo)..." -ForegroundColor Gray
$allSessions = Get-VBRBackupSession | Group-Object JobId -AsHashTable
$allAgentSessions = Get-VBRComputerBackupJobSession | Group-Object JobId -AsHashTable
# -------------------------------------------------------

$resultados = foreach ($job in $allJobs) {
    
    # Saltar trabajos de tipo EpAgentBackup
    if ($job.JobType -eq "EpAgentBackup") { continue }
    
    # Buscamos en el Hash Table en memoria (instantáneo)
    $session = $allSessions[$job.Id] | Sort-Object CreationTime -Descending | Select-Object -First 1
    
    if ($null -eq $session) {
        $session = $allAgentSessions[$job.Id] | Sort-Object CreationTime -Descending | Select-Object -First 1
    }
    
    # Si aún no hay sesión, intentar con Get-VBRSession (para Backup Copy)
    if ($null -eq $session -and $job.JobType -in @("SimpleBackupCopyPolicy", "BackupCopy")) {
        $session = Get-VBRSession -Job $job -WarningAction SilentlyContinue | 
                   Sort-Object CreationTime -Descending | 
                   Select-Object -First 1
    }

    # Determinar tipo de trabajo
    $tipo = switch ($job.JobType) {
        "Backup" { "Hyper-V" }
        "SimpleBackupCopyPolicy" { "Copy" }
        "BackupCopy" { "Copy" }
        default { "Agent" }
    }

    $resultadoTexto = "Sin datos"
    if ($null -ne $session) {
        $resultadoTexto = [string]$session.Result
    }

    [PSCustomObject]@{
        Trabajo    = $job.Name
        Tipo       = $tipo
        LastRun    = if ($session.EndTime) { $session.EndTime } elseif ($session.CreationTime) { $session.CreationTime } else { "Sin datos" }
        Estado     = if ($session.State) { [string]$session.State } else { "Finished" }
        LastResult = $resultadoTexto
    }
}

# --- MOSTRAR RESULTADOS ---
Write-Host "`n[REPORTE DE BACKUP VEEAM - $(Get-Date)]" -ForegroundColor Cyan
$resultados | Sort-Object Trabajo | Format-Table -AutoSize

$incidencias = $resultados | Where-Object { 
    $_.LastResult -notin @("Success", "Working", "En curso") 
}

if ($incidencias) {
    Write-Host "ATENCIÓN: Se han detectado problemas o falta de datos." -ForegroundColor Red
    exit 1
} else {
    Write-Host "OK: Todos los backups se han ejecutado correctamente." -ForegroundColor Green
    # Uso de Set-Content que es más rápido que Out-File para JSON
    $resultados | ConvertTo-Json -Compress | Set-Content ".\ficheros_json\veeam_status.json" -Encoding UTF8
    exit 0
}