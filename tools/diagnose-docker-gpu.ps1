# Diagnose Ollama in Docker: GPU detection + vision request timing.
# ASCII-only to avoid Windows PowerShell 5.1 encoding issues.
#
# Run from repo root:
#   PowerShell -ExecutionPolicy Bypass -File tools\diagnose-docker-gpu.ps1

$ErrorActionPreference = "Continue"

function Section($title) {
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host $title -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
}

# ----------------------------------------------------------------------------
Section "1. Host: NVIDIA driver"
# ----------------------------------------------------------------------------
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] nvidia-smi not on host. Install NVIDIA driver." -ForegroundColor Red
    exit 1
}

# ----------------------------------------------------------------------------
Section "2. Docker GPU passthrough (docker run --gpus all)"
# ----------------------------------------------------------------------------
docker info 2>&1 | Select-String -Pattern "WSL" -CaseSensitive:$false | Select-Object -First 1
$gpuTestOutput = docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi 2>&1 | Out-String
$gpuTestOutput.Split("`n") | Select-Object -First 12 | ForEach-Object { Write-Host $_ }
if ($gpuTestOutput -notmatch "NVIDIA-SMI") {
    Write-Host "[FAIL] Docker GPU passthrough not working" -ForegroundColor Red
    Write-Host "       Install NVIDIA Container Toolkit in WSL2"
    exit 1
}
Write-Host "[OK] Docker -> CUDA passthrough works" -ForegroundColor Green

# ----------------------------------------------------------------------------
Section "3. Start Ollama in Docker with GPU"
# ----------------------------------------------------------------------------
Write-Host "Stopping any existing ollama container..."
docker compose --profile local-llm stop ollama 2>$null | Out-Null
docker compose --profile local-llm rm -f ollama 2>$null | Out-Null

Write-Host "Starting Ollama with GPU override..."
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile local-llm up -d ollama
Start-Sleep 5

$running = (docker compose ps ollama 2>$null | Select-String "running")
if (-not $running) {
    Write-Host "[FAIL] Ollama container not running" -ForegroundColor Red
    docker compose logs ollama --tail 30
    exit 1
}
Write-Host "[OK] Ollama running" -ForegroundColor Green

# ----------------------------------------------------------------------------
Section "4. Ollama logs: did it find GPU?"
# ----------------------------------------------------------------------------
Start-Sleep 4
Write-Host "--- Lines mentioning library/cuda/gpu/inference ---"
docker compose logs ollama --tail 200 2>&1 | Select-String -Pattern "library|cuda|gpu|inference|compute|nvidia" -CaseSensitive:$false | Select-Object -First 20

# ----------------------------------------------------------------------------
Section "5. Pull model (if missing)"
# ----------------------------------------------------------------------------
$modelList = docker compose exec -T ollama ollama list 2>&1 | Out-String
if ($modelList -notmatch "gemma3:4b") {
    Write-Host "Pulling gemma3:4b ..."
    docker compose exec -T ollama ollama pull gemma3:4b
} else {
    Write-Host "[OK] gemma3:4b already present" -ForegroundColor Green
}

# ----------------------------------------------------------------------------
Section "6. CRITICAL: ollama ps - GPU or CPU?"
# ----------------------------------------------------------------------------
Write-Host "Warmup request (loads model into memory)..."
$warmup = @{ model = "gemma3:4b"; prompt = "hi"; stream = $false; keep_alive = "24h" } | ConvertTo-Json
try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/generate" -Method POST -Body $warmup -ContentType "application/json" -TimeoutSec 120 | Out-Null
} catch {
    Write-Host "[WARN] Warmup failed: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "ollama ps:"
docker compose exec -T ollama ollama ps
Write-Host ""
Write-Host "^^^ Look at PROCESSOR column. '100% GPU' = good. 'CPU' or '0% GPU' = problem."

# ----------------------------------------------------------------------------
Section "7. nvidia-smi inside ollama container"
# ----------------------------------------------------------------------------
docker compose exec -T ollama nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] nvidia-smi inside container failed" -ForegroundColor Yellow
}

# ----------------------------------------------------------------------------
Section "8. Vision request timing (2 runs)"
# ----------------------------------------------------------------------------
$img = (Get-ChildItem fixtures\screenshots -Recurse -Filter *.png | Where-Object { $_.Name -notlike "*.redacted*" } | Select-Object -First 1).FullName
Write-Host "Test image: $img"
$base64 = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes($img))

$body = @{
    model = "gemma3:4b"
    prompt = "Describe this screenshot in one sentence."
    images = @($base64)
    stream = $false
    keep_alive = "24h"
    options = @{ num_predict = 100; temperature = 0 }
} | ConvertTo-Json -Depth 4

# Run 1
Write-Host "Vision request #1 ..."
$t1 = Measure-Command {
    $script:r1 = Invoke-RestMethod -Uri "http://localhost:11434/api/generate" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 600
}
$t1sec = [Math]::Round($t1.TotalSeconds, 2)
$load1 = [Math]::Round($script:r1.load_duration / 1e9, 2)
$eval1 = [Math]::Round($script:r1.eval_duration / 1e9, 2)
Write-Host "  total=${t1sec}s load=${load1}s eval=${eval1}s"

# Run 2
Write-Host "Vision request #2 ..."
$t2 = Measure-Command {
    $script:r2 = Invoke-RestMethod -Uri "http://localhost:11434/api/generate" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 600
}
$t2sec = [Math]::Round($t2.TotalSeconds, 2)
$load2 = [Math]::Round($script:r2.load_duration / 1e9, 2)
$eval2 = [Math]::Round($script:r2.eval_duration / 1e9, 2)
Write-Host "  total=${t2sec}s load=${load2}s eval=${eval2}s"

# ----------------------------------------------------------------------------
Section "VERDICT"
# ----------------------------------------------------------------------------
if ($t2sec -lt 15) {
    Write-Host "[OK] Vision on GPU is fast (${t2sec}s/request)" -ForegroundColor Green
    Write-Host "Pipeline should complete on 68 screenshots in 10-15 minutes."
    Write-Host ""
    Write-Host "Run full pipeline with --profile local-llm"
} elseif ($t2sec -lt 60) {
    Write-Host "[WARN] Vision works but slower than expected (${t2sec}s/request)" -ForegroundColor Yellow
    Write-Host "Pipeline will take 30-50 minutes. Workable but not ideal."
} else {
    Write-Host "[FAIL] Vision is critically slow (${t2sec}s/request)" -ForegroundColor Red
    Write-Host "Pipeline will not finish - timeouts on every screenshot."
    Write-Host ""
    Write-Host "RECOMMENDATIONS (pick one):"
    Write-Host "  1. Check 'ollama ps' above - if CPU shown, WSL2 not passing GPU"
    Write-Host "  2. Use host-llm profile (Ollama natively on host)"
    Write-Host "  3. Switch to cloud LLM (LLM_PROFILE=cloud + API key)"
}

Write-Host ""
Write-Host "Done."
