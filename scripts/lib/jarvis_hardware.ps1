# JARVIS hardware detection + model/profile recommendations (Windows).
# Dot-source: . "$PSScriptRoot\lib\jarvis_hardware.ps1"

function Get-JarvisGpuInfo {
    $gpus = @()
    try {
        $gpus = Get-CimInstance Win32_VideoController -ErrorAction Stop |
            Where-Object { $_.Name -and $_.Name -notmatch 'Microsoft Basic|Remote' }
    } catch { }

    $primary = $gpus | Select-Object -First 1
    if (-not $primary) {
        return @{
            Vendor  = 'none'
            Name    = 'CPU only'
            VramMb  = 0
            Gpus    = @()
        }
    }

    $name = $primary.Name
    $vendor = 'unknown'
    if ($name -match 'NVIDIA|GeForce|RTX|GTX|Quadro') { $vendor = 'nvidia' }
    elseif ($name -match 'AMD|Radeon') { $vendor = 'amd' }
    elseif ($name -match 'Intel') { $vendor = 'intel' }

    $vramMb = 0
    if ($primary.AdapterRAM -and $primary.AdapterRAM -gt 0) {
        $vramMb = [int]($primary.AdapterRAM / 1MB)
        if ($vramMb -gt 65536) { $vramMb = 0 }
    }

    if ($vendor -eq 'nvidia' -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
        try {
            $smi = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
            if ($smi -match '^\d+$') { $vramMb = [int]$smi }
        } catch { }
    }

    @{
        Vendor = $vendor
        Name   = $name
        VramMb = $vramMb
        Gpus   = @($gpus | ForEach-Object { $_.Name })
    }
}

function Get-JarvisHardwareProfile {
    param([hashtable]$GpuInfo)

    $vendor = $GpuInfo.Vendor
    $vram = $GpuInfo.VramMb

    $profile = 'cpu'
    $ollamaVulkan = $false
    $chatModel = 'qwen2.5:3b-instruct'
    $agentModel = 'qwen2.5:3b-instruct'
    $whisperModel = 'base'
    $visionOnDemand = $false
    $notes = @()

    switch ($vendor) {
        'nvidia' {
            $profile = 'nvidia'
            $ollamaVulkan = $false
            $chatModel = 'gemma3:4b'
            if ($vram -ge 6144 -or $vram -eq 0) {
                $agentModel = 'qwen2.5:7b-instruct'
            } else {
                $agentModel = 'qwen2.5:3b-instruct'
                $notes += 'VRAM < 6 GB — agent model зменшено до qwen2.5:3b-instruct'
            }
            $whisperModel = 'small'
            if ($vram -gt 0 -and $vram -lt 10240) {
                $visionOnDemand = $true
                $notes += 'VRAM < 10 GB — OLLAMA_VISION_ON_DEMAND=true (vision за запитом)'
            }
            $notes += 'NVIDIA: CUDA автоматично, OLLAMA_VULKAN не потрібен'
        }
        'amd' {
            $profile = 'amd'
            $ollamaVulkan = $true
            $chatModel = 'gemma3:4b'
            $agentModel = 'qwen2.5:7b-instruct'
            $whisperModel = 'small'
            if ($vram -gt 0 -and $vram -le 9216) {
                $visionOnDemand = $true
                $notes += 'VRAM <= 8 GB — OLLAMA_VISION_ON_DEMAND=true'
            }
            $notes += 'AMD на Windows: OLLAMA_VULKAN=1 (Vulkan backend)'
        }
        default {
            $profile = 'cpu'
            $ollamaVulkan = $false
            $notes += 'CPU-only: non-thinking instruct-моделі (~7-8 tok/s); уникай qwen3/gemma thinking'
        }
    }

    $models = @($chatModel, $agentModel, 'nomic-embed-text') | Select-Object -Unique

    @{
        profile            = $profile
        gpu_vendor         = $vendor
        gpu_name           = $GpuInfo.Name
        vram_mb            = $vram
        ollama_vulkan      = $ollamaVulkan
        ollama_model_chat  = $chatModel
        ollama_model_agent = $agentModel
        embed_model        = 'nomic-embed-text'
        whisper_model      = $whisperModel
        vision_on_demand   = $visionOnDemand
        models             = $models
        notes              = $notes
        detected_at        = (Get-Date).ToString('o')
    }
}

function Save-JarvisHardwareProfile {
    param([string]$Root, [hashtable]$Profile)
    $dir = Join-Path $Root 'data'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $path = Join-Path $dir 'hardware_profile.json'
    $Profile | ConvertTo-Json -Depth 5 | Set-Content -Path $path -Encoding UTF8
    return $path
}

function Read-JarvisHardwareProfile {
    param([string]$Root)
    $path = Join-Path $Root 'data\hardware_profile.json'
    if (-not (Test-Path $path)) { return $null }
    try {
        $obj = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
        return @{
            profile            = $obj.profile
            gpu_vendor         = $obj.gpu_vendor
            gpu_name           = $obj.gpu_name
            vram_mb            = [int]$obj.vram_mb
            ollama_vulkan      = [bool]$obj.ollama_vulkan
            ollama_model_chat  = $obj.ollama_model_chat
            ollama_model_agent = $obj.ollama_model_agent
            embed_model        = $obj.embed_model
            whisper_model      = $obj.whisper_model
            vision_on_demand   = [bool]$obj.vision_on_demand
            models             = @($obj.models)
            notes              = @($obj.notes)
        }
    } catch { return $null }
}

function Get-JarvisOllamaUserEnv {
    param([hashtable]$Profile)
    $env = @{
        OLLAMA_HOST       = '0.0.0.0:11434'
        OLLAMA_KEEP_ALIVE = '24h'
    }
    if ($Profile.ollama_vulkan) {
        $env['OLLAMA_VULKAN'] = '1'
    }
    $env
}

function Apply-JarvisOllamaUserEnv {
    param([hashtable]$Profile)
    $ollamaEnv = Get-JarvisOllamaUserEnv -Profile $Profile
    foreach ($kv in $ollamaEnv.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($kv.Key, $kv.Value, 'User')
    }
    if (-not $Profile.ollama_vulkan) {
        [Environment]::SetEnvironmentVariable('OLLAMA_VULKAN', $null, 'User')
    }
    $ollamaEnv
}
