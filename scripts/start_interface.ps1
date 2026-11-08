[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$virtualEnvironmentDirectory = Join-Path $repositoryRoot '.venv'
$virtualEnvironmentPython = Join-Path $virtualEnvironmentDirectory 'Scripts\python.exe'
$applicationUrl = 'http://127.0.0.1:8501'
$previousPythonPath = $env:PYTHONPATH

Push-Location -LiteralPath $repositoryRoot
try {
    foreach ($serviceName in @('OracleServiceXE', 'OracleOraDB21Home1TNSListener')) {
        $oracleService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if (-not $oracleService) {
            throw "No se encuentra el servicio $serviceName. Este lanzador requiere Oracle XE instalado en este equipo."
        }
        if ($oracleService.Status -ne 'Running') {
            throw "El servicio $serviceName esta detenido. Abra services.msc, inicielo y vuelva a ejecutar run_app.cmd."
        }
    }
    Write-Host '[OK] Los servicios de Oracle estan iniciados.'

    if (-not (Test-Path -LiteralPath $virtualEnvironmentPython)) {
        if ($CheckOnly) {
            throw 'Falta el entorno .venv. Ejecute run_app.cmd sin -CheckOnly para prepararlo.'
        }
        Write-Host 'Preparando el entorno Python...'
        if (Get-Command py.exe -ErrorAction SilentlyContinue) {
            & py.exe -3 -m venv $virtualEnvironmentDirectory
        } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
            & python.exe -m venv $virtualEnvironmentDirectory
        } else {
            throw 'No se encuentra Python. Instale Python 3 con su lanzador py y vuelva a ejecutar run_app.cmd.'
        }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $virtualEnvironmentPython)) {
            throw 'No se pudo crear .venv. Revise el mensaje de Python mostrado arriba.'
        }
    }

    $dependencyCheck = @'
import importlib
import sys
try:
    for module_name in ('streamlit', 'oracledb', 'pandas', 'plotly', 'dotenv'):
        importlib.import_module(module_name)
except ImportError:
    sys.exit(1)
'@
    & $virtualEnvironmentPython -c $dependencyCheck
    if ($LASTEXITCODE -ne 0) {
        if ($CheckOnly) {
            throw 'Faltan dependencias. Ejecute run_app.cmd sin -CheckOnly para instalarlas.'
        }
        Write-Host 'Instalando las dependencias de app/requirements.txt. Esta fase necesita internet...'
        & $virtualEnvironmentPython -m pip install --disable-pip-version-check -r 'app/requirements.txt'
        if ($LASTEXITCODE -ne 0) {
            throw 'No se pudieron instalar las dependencias. Revise su conexion a internet y el mensaje anterior.'
        }
        & $virtualEnvironmentPython -c 'import streamlit, oracledb, pandas, plotly, dotenv'
        if ($LASTEXITCODE -ne 0) {
            throw 'Las dependencias no se pueden importar. Revise el error de Python mostrado arriba.'
        }
    }
    Write-Host '[OK] El entorno Python y las dependencias estan disponibles.'

    $listeningConnection = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listeningConnection) {
        $listeningProcess = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $listeningConnection.OwningProcess)
        $commandLine = [string]$listeningProcess.CommandLine
        $belongsToProject = $commandLine.IndexOf($virtualEnvironmentPython, [StringComparison]::OrdinalIgnoreCase) -ge 0
        $runsApplication = $commandLine -match 'streamlit\s+run\s+.*app[\\/]main\.py'
        if (-not ($belongsToProject -and $runsApplication)) {
            throw ("El puerto 8501 esta ocupado por otro proceso (PID {0}). Cierre esa aplicacion o revise su consola antes de continuar." -f $listeningConnection.OwningProcess)
        }
        $healthResponse = Invoke-WebRequest -Uri "$applicationUrl/_stcore/health" -UseBasicParsing -TimeoutSec 5
        if ($healthResponse.StatusCode -ne 200 -or ([string]$healthResponse.Content).Trim() -ne 'ok') {
            throw 'La instancia existente todavia no esta lista. Revise la ventana donde la inicio.'
        }
        Write-Host "[OK] TurismoUQ ya esta encendido: $applicationUrl"
        if (-not ($CheckOnly -or $NoBrowser)) {
            Start-Process $applicationUrl
        }
        return
    }

    if ($CheckOnly) {
        Write-Host '[OK] El puerto 8501 esta libre. Puede ejecutar run_app.cmd para abrir TurismoUQ.'
        return
    }

    $env:PYTHONPATH = $repositoryRoot
    $headlessValue = if ($NoBrowser) { 'true' } else { 'false' }
    Write-Host ''
    Write-Host "Abriendo TurismoUQ: $applicationUrl"
    Write-Host 'Mantenga esta ventana abierta. Para apagar la interfaz, presione Ctrl+C.'
    Write-Host ''
    & $virtualEnvironmentPython -m streamlit run 'app/main.py' `
        '--server.address=127.0.0.1' '--server.port=8501' `
        "--server.headless=$headlessValue" '--browser.gatherUsageStats=false'
    if ($LASTEXITCODE -ne 0) {
        throw 'Streamlit se detuvo. Revise el mensaje mostrado arriba.'
    }
} catch {
    Write-Host ("ERROR: {0}" -f $_.Exception.Message) -ForegroundColor Red
    exit 1
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
