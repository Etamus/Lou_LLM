param(
    [switch]$Silent,
    [string]$LogPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$script:ProjectRoot = Split-Path -Parent $PSCommandPath
$script:VenvDir = Join-Path $script:ProjectRoot ".venv"
$script:ModelsDir = Join-Path $script:ProjectRoot "models"
$script:LlamaRoot = Join-Path $script:ProjectRoot "llamacpp-server"
$script:LlamaBinDir = Join-Path $script:LlamaRoot "bin"
$script:DownloadRoot = Join-Path $script:ProjectRoot "downloads\llama.cpp"
$script:UiPercent = 0
$script:InstallLogPath = if ($LogPath) { [IO.Path]::GetFullPath($LogPath) } else { "" }

if ($script:InstallLogPath) {
    $logParent = Split-Path -Parent $script:InstallLogPath
    if ($logParent) {
        New-Item -ItemType Directory -Force -Path $logParent | Out-Null
    }
    Set-Content -LiteralPath $script:InstallLogPath -Value "" -Encoding UTF8
}

function Write-InstallLine {
    param([string]$Message)
    Write-Host $Message
    if ($script:InstallLogPath) {
        Add-Content -LiteralPath $script:InstallLogPath -Value $Message -Encoding UTF8
    }
}

function Send-InstallLog {
    param([string]$Message)
    Write-InstallLine ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

function Send-InstallProgress {
    param(
        [int]$Percent,
        [string]$Stage,
        [string]$Message
    )
    $script:UiPercent = [Math]::Max(0, [Math]::Min(100, $Percent))
    if ($Message) {
        Send-InstallLog $Message
    }
}

function Assert-UnderProject {
    param([string]$Path)
    $root = [IO.Path]::GetFullPath($script:ProjectRoot).TrimEnd("\") + "\"
    $full = [IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Caminho fora do projeto: $Path"
    }
}

function Invoke-CheckedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Description
    )

    Send-InstallLog $Description
    Push-Location $script:ProjectRoot
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($output) {
        foreach ($line in $output) {
            $text = $line.ToString().Trim()
            if ($text) {
                Send-InstallLog $text
            }
        }
    }
    if ($exitCode -ne 0) {
        throw "$Description falhou com codigo $exitCode."
    }
}

function Get-PythonCandidate {
    $candidates = @(
        @{ File = "python"; Args = @() },
        @{ File = "py"; Args = @("-3.11") },
        @{ File = "py"; Args = @("-3") }
    )

    foreach ($candidate in $candidates) {
        try {
            $versionOutput = & $candidate.File @($candidate.Args + @("--version")) 2>&1
            $versionText = ($versionOutput | Select-Object -First 1).ToString()
            if ($versionText -notmatch "Python\s+(\d+)\.(\d+)") {
                continue
            }
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
                return [pscustomobject]@{
                    File = $candidate.File
                    Args = [string[]]$candidate.Args
                    Version = $versionText
                }
            }
        } catch {
            continue
        }
    }

    throw "Python 3.11+ nao encontrado no PATH. Instale em https://www.python.org/downloads/ e marque Add Python to PATH."
}

function Get-LatestLlamaRelease {
    Send-InstallLog "Consultando ultimo release do llama.cpp no GitHub..."
    $headers = @{ "User-Agent" = "Loucpp-installer" }
    $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"

    $llamaAsset = $release.assets |
        Where-Object { $_.name -like "llama-*-bin-win-cuda-13.1-x64.zip" } |
        Select-Object -First 1
    $cudartAsset = $release.assets |
        Where-Object { $_.name -eq "cudart-llama-bin-win-cuda-13.1-x64.zip" } |
        Select-Object -First 1

    if (-not $llamaAsset) {
        throw "O release $($release.tag_name) nao possui pacote llama-*-bin-win-cuda-13.1-x64.zip."
    }
    if (-not $cudartAsset) {
        throw "O release $($release.tag_name) nao possui cudart-llama-bin-win-cuda-13.1-x64.zip."
    }

    [pscustomobject]@{
        Tag = $release.tag_name
        PublishedAt = $release.published_at
        LlamaAsset = $llamaAsset
        CudartAsset = $cudartAsset
    }
}

function Save-GitHubAsset {
    param(
        [object]$Asset,
        [string]$DestinationDir
    )
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    $destination = Join-Path $DestinationDir $Asset.name
    if ((Test-Path -LiteralPath $destination) -and ((Get-Item -LiteralPath $destination).Length -gt 0)) {
        $existing = Get-Item -LiteralPath $destination
        if (-not $Asset.size -or $existing.Length -eq [int64]$Asset.size) {
            Send-InstallLog "Arquivo ja baixado: $($Asset.name)"
            return $destination
        }
        Send-InstallLog "Download parcial detectado; baixando novamente: $($Asset.name)"
        Remove-Item -LiteralPath $destination -Force
    }

    Send-InstallLog "Baixando $($Asset.name)..."
    Invoke-WebRequest -UseBasicParsing -Uri $Asset.browser_download_url -OutFile $destination
    return $destination
}

function Install-LlamaCpp {
    Send-InstallProgress 35 "llama" "Preparando instalacao do llama.cpp CUDA 13.1..."
    $release = Get-LatestLlamaRelease
    $releaseDir = Join-Path $script:DownloadRoot $release.Tag

    $llamaZip = Save-GitHubAsset -Asset $release.LlamaAsset -DestinationDir $releaseDir
    Send-InstallProgress 55 "llama" "Pacote principal baixado: $($release.LlamaAsset.name)"

    $cudartZip = Save-GitHubAsset -Asset $release.CudartAsset -DestinationDir $releaseDir
    Send-InstallProgress 68 "llama" "DLLs CUDA 13.1 baixadas: $($release.CudartAsset.name)"

    Assert-UnderProject $script:LlamaRoot
    Assert-UnderProject $script:LlamaBinDir
    if (Test-Path -LiteralPath $script:LlamaBinDir) {
        Remove-Item -LiteralPath $script:LlamaBinDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $script:LlamaBinDir | Out-Null

    Send-InstallProgress 76 "llama" "Extraindo llama.cpp no projeto..."
    Expand-Archive -LiteralPath $llamaZip -DestinationPath $script:LlamaBinDir -Force
    Expand-Archive -LiteralPath $cudartZip -DestinationPath $script:LlamaBinDir -Force

    $serverExe = Get-ChildItem -LiteralPath $script:LlamaBinDir -Recurse -Filter "llama-server.exe" -File |
        Select-Object -First 1
    if (-not $serverExe) {
        throw "llama-server.exe nao encontrado depois da extracao."
    }

    $versionText = @(
        "tag=$($release.Tag)"
        "published_at=$($release.PublishedAt)"
        "installed_at=$((Get-Date).ToString('s'))"
        "llama_asset=$($release.LlamaAsset.name)"
        "llama_url=$($release.LlamaAsset.browser_download_url)"
        "cudart_asset=$($release.CudartAsset.name)"
        "cudart_url=$($release.CudartAsset.browser_download_url)"
        "server_exe=$($serverExe.FullName)"
    ) -join [Environment]::NewLine
    New-Item -ItemType Directory -Force -Path $script:LlamaRoot | Out-Null
    Set-Content -LiteralPath (Join-Path $script:LlamaRoot "version.txt") -Value $versionText -Encoding UTF8

    Send-InstallProgress 84 "llama" "llama.cpp $($release.Tag) instalado."
}

function Invoke-LouInstall {
    Send-InstallProgress 4 "python" "Verificando Python 3.11+..."
    $python = Get-PythonCandidate
    Send-InstallLog "Encontrado: $($python.Version)"

    if (-not (Test-Path -LiteralPath (Join-Path $script:VenvDir "Scripts\python.exe"))) {
        Send-InstallProgress 12 "venv" "Criando ambiente virtual .venv..."
        Invoke-CheckedProcess -FilePath $python.File -Arguments @($python.Args + @("-m", "venv", $script:VenvDir)) -Description "Criacao da venv"
    } else {
        Send-InstallProgress 18 "venv" "Ambiente virtual .venv ja existe."
    }

    $venvPython = Join-Path $script:VenvDir "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "Python da venv nao encontrado em $venvPython"
    }

    Send-InstallProgress 24 "venv" "Atualizando pip..."
    Invoke-CheckedProcess -FilePath $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "--quiet") -Description "Atualizacao do pip"

    Install-LlamaCpp

    Send-InstallProgress 90 "folders" "Garantindo pastas do projeto..."
    New-Item -ItemType Directory -Force -Path $script:ModelsDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $script:ProjectRoot "data") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $script:ProjectRoot "assets\avatars") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $script:ProjectRoot "assets\gifs") | Out-Null

    $modelCount = @(
        Get-ChildItem -LiteralPath $script:ModelsDir -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension.ToLowerInvariant() -in @(".gguf", ".bin") }
    ).Count
    if ($modelCount -eq 0) {
        Send-InstallLog "Nenhum modelo GGUF encontrado em models. Coloque um .gguf nessa pasta para ativar a IA."
    } else {
        Send-InstallLog "$modelCount modelo(s) encontrado(s) em models."
    }

    Send-InstallProgress 100 "done" "Instalacao concluida. Use iniciar.bat para abrir a Lou."
}

function Quote-ProcessArgument {
    param([string]$Value)
    '"' + ($Value -replace '"', '\"') + '"'
}

function Show-InstallerWindow {
    Add-Type -AssemblyName PresentationFramework
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase

    $xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Loucpp - Instalador"
        Width="780" Height="560"
        WindowStartupLocation="CenterScreen"
        ResizeMode="NoResize"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent"
        FontFamily="Segoe UI">
    <Window.Resources>
        <Style x:Key="PrimaryButton" TargetType="{x:Type Button}">
            <Setter Property="Background" Value="#111111"/>
            <Setter Property="Foreground" Value="#FFFFFF"/>
            <Setter Property="BorderThickness" Value="0"/>
            <Setter Property="Padding" Value="22,9"/>
            <Setter Property="FontSize" Value="13"/>
            <Setter Property="FontWeight" Value="SemiBold"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="{x:Type Button}">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#262626"/>
                            </Trigger>
                            <Trigger Property="IsEnabled" Value="False">
                                <Setter TargetName="bd" Property="Opacity" Value="0.45"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
        <Style x:Key="GhostButton" TargetType="{x:Type Button}" BasedOn="{StaticResource PrimaryButton}">
            <Setter Property="Background" Value="#F4F4F5"/>
            <Setter Property="Foreground" Value="#111111"/>
            <Setter Property="FontWeight" Value="Normal"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="{x:Type Button}">
                        <Border x:Name="bd" Background="{TemplateBinding Background}" CornerRadius="8" Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                        <ControlTemplate.Triggers>
                            <Trigger Property="IsMouseOver" Value="True">
                                <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                            </Trigger>
                        </ControlTemplate.Triggers>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </Window.Resources>

    <Border CornerRadius="14" Background="#FAFAFA" BorderBrush="#E4E4E7" BorderThickness="1">
        <Border.Effect>
            <DropShadowEffect Color="#000000" BlurRadius="42" ShadowDepth="0" Opacity="0.24"/>
        </Border.Effect>
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="56"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="68"/>
            </Grid.RowDefinitions>

            <Grid Grid.Row="0" Background="Transparent">
                <Grid.ColumnDefinitions>
                    <ColumnDefinition Width="*"/>
                    <ColumnDefinition Width="Auto"/>
                </Grid.ColumnDefinitions>
                <StackPanel Orientation="Horizontal" Margin="18,0,0,0" VerticalAlignment="Center">
                    <Border Width="22" Height="22" CornerRadius="6" Background="#111111" Margin="0,0,10,0">
                        <TextBlock Text="L" Foreground="#FFFFFF" FontSize="12" FontWeight="SemiBold" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                    </Border>
                    <TextBlock Text="Loucpp" FontSize="15" FontWeight="SemiBold" Foreground="#111111" VerticalAlignment="Center"/>
                    <TextBlock Text="  -  Instalador" FontSize="13" Foreground="#71717A" VerticalAlignment="Center"/>
                </StackPanel>
                <Button x:Name="WindowCloseButton" Grid.Column="1" Width="44" Height="32" Margin="0,0,12,0"
                        Background="Transparent" BorderThickness="0" Cursor="Hand">
                    <Button.Template>
                        <ControlTemplate TargetType="{x:Type Button}">
                            <Border x:Name="bd" Background="Transparent" CornerRadius="6">
                                <TextBlock Text="X" FontSize="13" Foreground="#71717A" HorizontalAlignment="Center" VerticalAlignment="Center"/>
                            </Border>
                            <ControlTemplate.Triggers>
                                <Trigger Property="IsMouseOver" Value="True">
                                    <Setter TargetName="bd" Property="Background" Value="#E4E4E7"/>
                                </Trigger>
                            </ControlTemplate.Triggers>
                        </ControlTemplate>
                    </Button.Template>
                </Button>
            </Grid>

            <Grid Grid.Row="1" Margin="32,8,32,0">
                <Grid Name="ConfigPanel">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,18">
                        <TextBlock Text="Instala&#xE7;&#xE3;o da Lou" FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock Text="Vamos preparar o ambiente local e baixar o llama.cpp mais recente." FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="#FFFFFF" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="20">
                        <Grid>
                            <Grid.ColumnDefinitions>
                                <ColumnDefinition Width="*"/>
                                <ColumnDefinition Width="*"/>
                            </Grid.ColumnDefinitions>
                            <StackPanel Grid.Column="0" Margin="0,0,22,0">
                                <TextBlock Text="O que ser&#xE1; instalado" FontWeight="SemiBold" FontSize="13" Foreground="#111111" Margin="0,0,0,10"/>
                                <TextBlock Name="StatusPython" Text="- Python 3.11+ e ambiente virtual .venv" FontSize="12" Foreground="#52525B" Margin="0,0,0,6"/>
                                <TextBlock Name="StatusVenv" Text="- pip atualizado dentro da venv" FontSize="12" Foreground="#52525B" Margin="0,0,0,6"/>
                                <TextBlock Name="StatusLlama" Text="- llama.cpp latest CUDA 13.1 + cudart" FontSize="12" Foreground="#52525B" Margin="0,0,0,6"/>
                                <TextBlock Name="StatusFolders" Text="- Pastas models, data e assets" FontSize="12" Foreground="#52525B"/>
                            </StackPanel>
                            <StackPanel Grid.Column="1">
                                <TextBlock Text="Destino" FontWeight="SemiBold" FontSize="13" Foreground="#111111" Margin="0,0,0,10"/>
                                <TextBlock Text="llamacpp-server\bin" FontFamily="Consolas" FontSize="12" Foreground="#52525B" Margin="0,0,0,4"/>
                                <TextBlock Text="models\" FontFamily="Consolas" FontSize="12" Foreground="#52525B" Margin="0,0,0,14"/>
                                <Border Background="#FAFAFA" CornerRadius="8" Padding="14,12">
                                    <TextBlock Text="Os bin&#xE1;rios CUDA ficam no projeto. N&#xE3;o depende do CUDA Toolkit em Program Files." FontSize="12" Foreground="#71717A" TextWrapping="Wrap"/>
                                </Border>
                            </StackPanel>
                        </Grid>
                    </Border>
                </Grid>

                <Grid Name="InstallPanel" Visibility="Collapsed">
                    <Grid.RowDefinitions>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="Auto"/>
                        <RowDefinition Height="*"/>
                    </Grid.RowDefinitions>

                    <StackPanel Grid.Row="0" Margin="0,0,0,12">
                        <TextBlock Text="Instalando..." FontSize="22" FontWeight="SemiBold" Foreground="#111111"/>
                        <TextBlock Name="StageText" Text="Preparando..." FontSize="13" Foreground="#71717A" Margin="0,4,0,0"/>
                    </StackPanel>

                    <Border Grid.Row="1" Background="#FFFFFF" CornerRadius="10" BorderBrush="#E4E4E7" BorderThickness="1" Padding="16,14" Margin="0,0,0,14">
                        <StackPanel>
                            <Grid>
                                <TextBlock Text="Progresso" FontSize="12" Foreground="#52525B"/>
                                <TextBlock Name="ProgressLabel" Text="0%" FontSize="12" Foreground="#52525B" HorizontalAlignment="Right"/>
                            </Grid>
                            <ProgressBar Name="InstallProgress" Height="6" Minimum="0" Maximum="100" Value="0" Margin="0,8,0,0"
                                         Foreground="#111111" Background="#F4F4F5" BorderThickness="0"/>
                        </StackPanel>
                    </Border>

                    <Border Grid.Row="2" Background="#0A0A0A" CornerRadius="10" Padding="14,12">
                        <TextBox Name="LogBox" Background="Transparent" Foreground="#D4D4D4" BorderThickness="0"
                                 IsReadOnly="True" FontFamily="Consolas" FontSize="11" TextWrapping="Wrap"
                                 AcceptsReturn="True" VerticalScrollBarVisibility="Auto"/>
                    </Border>
                </Grid>
            </Grid>

            <Border Grid.Row="2" BorderBrush="#EEEEEE" BorderThickness="0,1,0,0" Padding="32,0,32,0">
                <StackPanel Orientation="Horizontal" HorizontalAlignment="Right" VerticalAlignment="Center">
                    <Button Name="OpenModelsButton" Style="{StaticResource GhostButton}" Content="Abrir models" Margin="0,0,10,0"/>
                    <Button Name="InstallButton" Style="{StaticResource PrimaryButton}" Content="Instalar"/>
                </StackPanel>
            </Border>
        </Grid>
    </Border>
</Window>
"@

    $stringReader = [System.IO.StringReader]::new([string]$xaml)
    $reader = [System.Xml.XmlReader]::Create([System.IO.TextReader]$stringReader)
    $window = [Windows.Markup.XamlReader]::Load([System.Xml.XmlReader]$reader)

    $installButton = $window.FindName("InstallButton")
    $windowCloseButton = $window.FindName("WindowCloseButton")
    $openModelsButton = $window.FindName("OpenModelsButton")
    $configPanel = $window.FindName("ConfigPanel")
    $installPanel = $window.FindName("InstallPanel")
    $progress = $window.FindName("InstallProgress")
    $progressLabel = $window.FindName("ProgressLabel")
    $logBox = $window.FindName("LogBox")
    $stageText = $window.FindName("StageText")
    $statusPython = $window.FindName("StatusPython")
    $statusVenv = $window.FindName("StatusVenv")
    $statusLlama = $window.FindName("StatusLlama")
    $statusFolders = $window.FindName("StatusFolders")

    $setPercent = {
        param([int]$Value)
        $bounded = [Math]::Max(0, [Math]::Min(100, $Value))
        $progress.Value = $bounded
        if ($progressLabel) {
            $progressLabel.Text = "$bounded%"
        }
    }

    $setStage = {
        param([string]$Stage)
        $doneBrush = [Windows.Media.Brushes]::DarkGreen
        switch ($Stage) {
            "python" { $statusPython.Foreground = $doneBrush }
            "venv" { $statusPython.Foreground = $doneBrush; $statusVenv.Foreground = $doneBrush }
            "llama" { $statusPython.Foreground = $doneBrush; $statusVenv.Foreground = $doneBrush; $statusLlama.Foreground = $doneBrush }
            "folders" { $statusFolders.Foreground = $doneBrush }
            "done" {
                $statusPython.Foreground = $doneBrush
                $statusVenv.Foreground = $doneBrush
                $statusLlama.Foreground = $doneBrush
                $statusFolders.Foreground = $doneBrush
            }
        }
    }

    $applyLogProgress = {
        param([string]$Line)
        if ($Line -match "Verificando Python") {
            & $setPercent 4
            $stageText.Text = "Verificando Python 3.11+..."
            & $setStage "python"
        } elseif ($Line -match "Criando ambiente|Ambiente virtual") {
            & $setPercent 18
            $stageText.Text = "Preparando ambiente virtual..."
            & $setStage "venv"
        } elseif ($Line -match "Atualizando pip") {
            & $setPercent 24
            $stageText.Text = "Atualizando pip..."
            & $setStage "venv"
        } elseif ($Line -match "Preparando instalacao") {
            & $setPercent 35
            $stageText.Text = "Consultando llama.cpp..."
            & $setStage "llama"
        } elseif ($Line -match "Pacote principal baixado") {
            & $setPercent 55
            $stageText.Text = "Pacote principal baixado"
            & $setStage "llama"
        } elseif ($Line -match "DLLs CUDA") {
            & $setPercent 68
            $stageText.Text = "DLLs CUDA baixadas"
            & $setStage "llama"
        } elseif ($Line -match "Extraindo llama.cpp") {
            & $setPercent 76
            $stageText.Text = "Extraindo arquivos..."
            & $setStage "llama"
        } elseif ($Line -match "llama.cpp .* instalado") {
            & $setPercent 84
            $stageText.Text = "llama.cpp instalado"
            & $setStage "llama"
        } elseif ($Line -match "Garantindo pastas") {
            & $setPercent 90
            $stageText.Text = "Verificando pastas do projeto..."
            & $setStage "folders"
        } elseif ($Line -match "Instalacao concluida") {
            & $setPercent 100
            $stageText.Text = "Instalacao concluida"
            & $setStage "done"
        }
    }

    $window.Add_MouseLeftButtonDown({
        param($sender, $eventArgs)
        if ($eventArgs.ButtonState -eq "Pressed") {
            try { $window.DragMove() } catch {}
        }
    })

    $windowCloseButton.Add_Click({ $window.Close() })
    $openModelsButton.Add_Click({
        New-Item -ItemType Directory -Force -Path $script:ModelsDir | Out-Null
        Start-Process explorer.exe -ArgumentList "`"$script:ModelsDir`""
    })

    $script:GuiInstallProcess = $null
    $script:GuiInstallTimer = $null
    $script:GuiInstallLogPath = ""
    $script:GuiInstallLastLogText = ""

    $installButton.Add_Click({
        $installButton.IsEnabled = $false
        $windowCloseButton.IsEnabled = $false
        $installButton.Content = "Instalando..."
        $configPanel.Visibility = "Collapsed"
        $installPanel.Visibility = "Visible"
        $stageText.Text = "Instalando"
        & $setPercent 0
        $logBox.Clear()

        $scriptName = [IO.Path]::GetFileNameWithoutExtension($PSCommandPath)
        $script:GuiInstallLogPath = Join-Path ([IO.Path]::GetTempPath()) ("{0}-{1}.log" -f $scriptName, [guid]::NewGuid().ToString("N"))
        $script:GuiInstallLastLogText = ""
        Set-Content -LiteralPath $script:GuiInstallLogPath -Value "" -Encoding UTF8

        $psi = [Diagnostics.ProcessStartInfo]::new()
        $psi.FileName = "powershell"
        $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File $(Quote-ProcessArgument $PSCommandPath) -Silent -LogPath $(Quote-ProcessArgument $script:GuiInstallLogPath)"
        $psi.WorkingDirectory = $script:ProjectRoot
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true

        try {
            $script:GuiInstallProcess = [Diagnostics.Process]::Start($psi)
        } catch {
            $installButton.IsEnabled = $true
            $windowCloseButton.IsEnabled = $true
            $installButton.Content = "Instalar"
            $stageText.Text = "Falha ao iniciar instalador"
            [Windows.MessageBox]::Show($_.Exception.Message, "Instalacao falhou", "OK", "Error") | Out-Null
            return
        }

        $script:GuiInstallTimer = [Windows.Threading.DispatcherTimer]::new()
        $script:GuiInstallTimer.Interval = [TimeSpan]::FromMilliseconds(250)
        $script:GuiInstallTimer.Add_Tick({
            if (Test-Path -LiteralPath $script:GuiInstallLogPath) {
                $currentText = Get-Content -LiteralPath $script:GuiInstallLogPath -Raw -Encoding UTF8
                if ($currentText.Length -gt $script:GuiInstallLastLogText.Length) {
                    $delta = $currentText.Substring($script:GuiInstallLastLogText.Length)
                    $script:GuiInstallLastLogText = $currentText
                    foreach ($line in ($delta -split "\r?\n")) {
                        $trimmed = $line.Trim()
                        if (-not $trimmed) {
                            continue
                        }
                        $logBox.AppendText($trimmed + [Environment]::NewLine)
                        $logBox.ScrollToEnd()
                        & $applyLogProgress $trimmed
                    }
                }
            }

            if ($script:GuiInstallProcess -and $script:GuiInstallProcess.HasExited) {
                $script:GuiInstallTimer.Stop()
                $installButton.IsEnabled = $true
                $windowCloseButton.IsEnabled = $true
                $installButton.Content = "Instalar"

                if ($script:GuiInstallProcess.ExitCode -eq 0) {
                    & $setPercent 100
                    $stageText.Text = "Instalacao concluida"
                    & $setStage "done"
                    [Windows.MessageBox]::Show("Tudo pronto. Agora use iniciar.bat para abrir a Lou.", "Instalacao concluida", "OK", "Information") | Out-Null
                } else {
                    $stageText.Text = "Falha na instalacao"
                    $message = "O instalador terminou com codigo $($script:GuiInstallProcess.ExitCode). Confira o log na tela."
                    $logBox.AppendText("[ERRO] " + $message + [Environment]::NewLine)
                    $logBox.ScrollToEnd()
                    [Windows.MessageBox]::Show($message, "Instalacao falhou", "OK", "Error") | Out-Null
                }
                $script:GuiInstallProcess.Dispose()
                $script:GuiInstallProcess = $null
                if (Test-Path -LiteralPath $script:GuiInstallLogPath) {
                    Remove-Item -LiteralPath $script:GuiInstallLogPath -Force -ErrorAction SilentlyContinue
                }
            } else {
                $current = [int]$progress.Value
                & $setPercent ([Math]::Min(96, [Math]::Max($current, 2)))
            }
        })
        $script:GuiInstallTimer.Start()
    })

    [void]$window.ShowDialog()
}

try {
    if ($Silent) {
        Invoke-LouInstall
    } else {
        Show-InstallerWindow
    }
    exit 0
} catch {
    Write-Host "[ERRO] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
