# Sync the bundled python engine (python/core) from the upstream multi_agent_translator checkout.
#
# The plugin ships a self-contained snapshot of the translation engine's non-LLM parts
# (extractor / tag_protector / chunker / assembler). Run this after upstream changes:
#
#   powershell -File scripts/sync-python-engine.ps1                    # default: sync core/
#   powershell -File scripts/sync-python-engine.ps1 -IncludeHelper     # also overwrite local_helper.py
#
# Notes:
# - python/local_helper.py is the PLUGIN-OWNED CLI adapter (adds UTF-8 stdout
#   reconfiguration and the lightweight `inspect` command). It is NOT overwritten
#   unless -IncludeHelper is passed; upstream CLI changes then need a manual merge.
# - __pycache__ directories are never copied.
param(
    [string]$Source,
    [switch]$IncludeHelper
)

$ErrorActionPreference = 'Stop'
$pluginRoot = Split-Path $PSScriptRoot -Parent
if (-not $Source) {
    # $PSScriptRoot 在 param 默认值中不可用，故在脚本体内计算默认源路径
    $Source = Join-Path (Split-Path $pluginRoot -Parent) 'multi_agent_translator'
}
$targetCore = Join-Path $pluginRoot 'python\core'
$sourceCore = Join-Path $Source 'core'
$sourceHelper = Join-Path $Source 'local_helper.py'

if (-not (Test-Path $sourceCore)) {
    throw "上游引擎目录不存在: $sourceCore（可用 -Source 指定 multi_agent_translator 路径）"
}

# 1. core/ 全量同步（删除目标中上游已移除的文件）
if (Test-Path $targetCore) { Remove-Item $targetCore -Recurse -Force }
Copy-Item $sourceCore $targetCore -Recurse
Get-ChildItem $targetCore -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
Write-Output "已同步 core/ -> $targetCore"

# 2. local_helper.py 仅在显式要求时覆盖
if ($IncludeHelper) {
    Copy-Item $sourceHelper (Join-Path $pluginRoot 'python\local_helper.py') -Force
    Write-Output "已覆盖 local_helper.py（注意：插件版定制了 UTF-8 输出与 inspect 命令，如有冲突需手动合并）"
} else {
    Write-Output "跳过 local_helper.py（插件版包含 UTF-8 修复与 inspect 命令；如需覆盖请加 -IncludeHelper）"
}

# 3. 提示运行测试
Write-Output "建议运行: python -m unittest discover -s test -v"
