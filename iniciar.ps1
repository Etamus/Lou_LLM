param(
    [switch]$NoInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSCommandPath
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Installer = Join-Path $ProjectRoot "instalar.ps1"
$LlamaRoot = Join-Path $ProjectRoot "llamacpp-server"
$Url = "http://127.0.0.1:8765"
$AppWidth = 1280
$AppHeight = 720

Add-Type -AssemblyName System.Windows.Forms
Add-Type @"
using System;
using System.Runtime.InteropServices;

public static class LouWindowTools {
    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
}
"@

function Test-LlamaCppInstalled {
    if (-not (Test-Path -LiteralPath $LlamaRoot)) {
        return $false
    }
    $server = Get-ChildItem -LiteralPath $LlamaRoot -Recurse -Filter "llama-server.exe" -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return [bool]$server
}

function Ensure-Installed {
    $missing = @()
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $missing += ".venv"
    }
    if (-not (Test-LlamaCppInstalled)) {
        $missing += "llama.cpp CUDA 13.1"
    }

    if ($missing.Count -eq 0) {
        return
    }

    if ($NoInstall) {
        throw "Instalacao incompleta: $($missing -join ', '). Execute instalar.bat."
    }

    Write-Host "[Lou] Instalacao incompleta: $($missing -join ', ')."
    Write-Host "[Lou] Executando instalador em modo automatico..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File $Installer -Silent
    if ($LASTEXITCODE -ne 0) {
        throw "Instalador falhou com codigo $LASTEXITCODE."
    }
}

function Wait-HttpReady {
    param(
        [string]$ReadyUrl,
        [Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            throw "Servidor encerrou antes de ficar pronto."
        }
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $ReadyUrl -TimeoutSec 2 | Out-Null
            return
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Servidor nao respondeu em $ReadyUrl dentro de $TimeoutSeconds segundos."
}

function Get-BrowserCommand {
    if ($env:LOU_BROWSER -and (Test-Path -LiteralPath $env:LOU_BROWSER)) {
        return [pscustomobject]@{ Path = $env:LOU_BROWSER; Kind = "chromium" }
    }

    $known = @(
        @{ Kind = "chromium"; Command = "msedge"; Paths = @("$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe", "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe") },
        @{ Kind = "chromium"; Command = "chrome"; Paths = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") },
        @{ Kind = "chromium"; Command = "brave"; Paths = @("$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe", "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe", "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe") },
        @{ Kind = "firefox"; Command = "firefox"; Paths = @("$env:ProgramFiles\Mozilla Firefox\firefox.exe", "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe") }
    )

    try {
        $userChoice = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice" -ErrorAction Stop
        $preferred = switch -Regex ($userChoice.ProgId) {
            "Chrome" { "chrome"; break }
            "Brave" { "brave"; break }
            "Firefox" { "firefox"; break }
            "MSEdge" { "msedge"; break }
            default { $null }
        }
        if ($preferred) {
            $known = @($known | Sort-Object {
                if ($_.Command -eq $preferred) { 0 } else { 1 }
            })
        }
    } catch {
        # Keep the built-in preference order if Windows does not expose UserChoice.
    }

    foreach ($item in $known) {
        $cmd = Get-Command $item.Command -ErrorAction SilentlyContinue
        if ($cmd) {
            return [pscustomobject]@{ Path = $cmd.Source; Kind = $item.Kind }
        }
        foreach ($path in $item.Paths) {
            if ($path -and (Test-Path -LiteralPath $path)) {
                return [pscustomobject]@{ Path = $path; Kind = $item.Kind }
            }
        }
    }

    return $null
}

function Center-AppProcessWindow {
    param(
        [Diagnostics.Process]$Process,
        [int]$Width,
        [int]$Height,
        [int]$Left,
        [int]$Top
    )

    if (-not $Process) {
        return
    }

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($Process.HasExited) {
            return
        }

        try {
            $Process.Refresh()
            if ($Process.MainWindowHandle -ne [IntPtr]::Zero) {
                [LouWindowTools]::MoveWindow($Process.MainWindowHandle, $Left, $Top, $Width, $Height, $true) | Out-Null
                return
            }
        } catch {
            return
        }

        Start-Sleep -Milliseconds 150
    }
}

function Open-AppWindow {
    param([string]$AppUrl)

    $browser = Get-BrowserCommand
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $width = [Math]::Min($AppWidth, [int]$screen.Width)
    $height = [Math]::Min($AppHeight, [int]$screen.Height)
    $left = [Math]::Max([int]$screen.Left, [int]($screen.Left + (($screen.Width - $width) / 2)))
    $top = [Math]::Max([int]$screen.Top, [int]($screen.Top + (($screen.Height - $height) / 2)))

    if ($browser -and $browser.Kind -eq "chromium") {
        $profileDir = Join-Path $ProjectRoot ".lou-webview-profile"
        New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
        Write-Host "[Lou] Abrindo em janela de aplicativo: $($browser.Path)"
        $process = Start-Process -FilePath $browser.Path -ArgumentList @(
            "--app=$AppUrl",
            "--new-window",
            "--user-data-dir=$profileDir",
            "--window-size=$width,$height",
            "--window-position=$left,$top",
            "--no-first-run"
        ) -PassThru
        Center-AppProcessWindow -Process $process -Width $width -Height $height -Left $left -Top $top
        return $process
    }

    if ($browser -and $browser.Kind -eq "firefox") {
        Write-Host "[Lou] Abrindo em janela do Firefox."
        $process = Start-Process -FilePath $browser.Path -ArgumentList @(
            "-new-window",
            $AppUrl,
            "-width",
            "$width",
            "-height",
            "$height"
        ) -PassThru
        Center-AppProcessWindow -Process $process -Width $width -Height $height -Left $left -Top $top
        return $process
    }

    Write-Host "[Lou] Navegador em modo app nao encontrado; abrindo navegador padrao."
    Start-Process $AppUrl
    return $null
}

try {
    Ensure-Installed

    $env:LOU_HOST = "127.0.0.1"
    $env:LOU_PORT = "8765"
    $env:LOU_OPEN_BROWSER = "0"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    Write-Host "[Lou] Iniciando backend local..."
    $serverProcess = Start-Process -FilePath $VenvPython `
        -ArgumentList @("run_neve_frontend.py", "--no-browser") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru

    try {
        Wait-HttpReady -ReadyUrl "$Url/api/bootstrap" -Process $serverProcess
        $browserProcess = Open-AppWindow -AppUrl $Url

        Write-Host "[Lou] Pronto em $Url"
        Write-Host "[Lou] Feche a janela do app para encerrar. Se ela nao fechar o servidor, pressione Ctrl+C aqui."

        if ($browserProcess) {
            try {
                Wait-Process -Id $browserProcess.Id
            } catch {
                Read-Host "Pressione Enter para encerrar a Lou"
            }
        } else {
            Read-Host "Pressione Enter para encerrar a Lou"
        }
    } finally {
        if ($serverProcess -and -not $serverProcess.HasExited) {
            Write-Host "[Lou] Encerrando backend..."
            Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
        }
    }
    exit 0
} catch {
    Write-Host "[ERRO] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
