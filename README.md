# 📖 dsh-plugin-text-translation

> **DeepSeek Harness (DSH) 文本与文档翻译插件**：为 DSH Agent 提供**标签防爆遮罩**、
> **多格式文本提取/切片**与**无损回填组装**能力，覆盖游戏脚本与长文档两类场景。
> 翻译本身由 DSH Agent 编排完成——可借助 DSH 内置的 `subagent` / `subagent_fork` /
> `workflow` 工具并行翻译各批次，本插件只负责"提取"与"装配"这两个原子环节。

- 📦 GitHub: https://github.com/1738348785/dsh-plugin-text-translation
- ✅ 实测环境：DSH `0.1.0-rc.6`（headless 与 web profile 均已验证）

---

## 🌟 核心特性

- 🛡️ **标签防爆遮罩 (Tag Protector)**：自动识别并保护 RPG Maker (`\c[1]`, `\v[1]`, `\n`)、
  Unity/RichText (`<color>`, `<b>`)、变量占位符 (`{player}`, `{0}`, `%s`) 与 Ren'Py 标签，
  翻译后 **100% 精确无损还原**。
- 📑 **全格式支持**：
  - **游戏脚本**：Mtool JSON (`ManualTransFile.json`)、Translator++ 表格 (XLSX/CSV)、
    Ren'Py (`.rpy`)、字幕 (SRT/ASS/VTT)、Gettext (`.po`)。
  - **长文档**：PDF、Word (`.docx`)、Markdown、HTML、TXT。
- 🧩 **原生集成 DSH**：
  - 导出标准的 `dsh.bundle` Manifest（`dsh.bundle.patch`），随 `dsh plugin` 安装后自动加入
    profile 的 bundle 层。
  - 注册 `extract_text`、`assemble_text`、`inspect_text_file` 三个工具供 DSH Agent 调度。
  - Python 引擎（`python/` 目录）随插件一起分发，安装即用，无外部路径依赖。

---

## 📦 安装与使用

### 方式一：从 GitHub 安装（推荐）

```bash
dsh plugin --profile demo add github:1738348785/dsh-plugin-text-translation
```

`dsh` 会拉取仓库、自动把插件的 `cordis.patch.yml` 追加进 profile 的 bundle 层。
（GitHub 安装实测通过：依赖走 pnpm store，无符号链接解析问题。）

### 方式二：安装到 web profile（让 GUI 插件页可见）

DSH Web 的「设置 → 插件」清单显示的是**当前运行的 profile 实际加载的插件**。
要让 GUI 里看到并管理本插件，需要装进 web profile 并重启：

```bash
dsh plugin --profile web add github:1738348785/dsh-plugin-text-translation
# 重启 web（Ctrl+C 后重新 dsh web），刷新页面即可在插件清单中看到 text-translation
```

### 方式三：本地源码安装（开发调试）

```bash
dsh plugin --profile demo add ./dsh-plugin-text-translation
```

> ⚠️ **注意**：pnpm 对本地路径包使用符号链接（junction），而 Node ESM 会按符号链接的
> **真实路径**解析依赖——插件代码 `import '@deepseek-ai/dsh-tools'` 时会从插件源码目录
> 向上查找，找不到 profile 里的依赖包并报 `ERR_MODULE_NOT_FOUND`。解决办法（Windows）：
> 把依赖树以 junction 暴露给插件目录（一次即可）：
>
> ```powershell
> # demo profile 有自己的依赖树时：
> New-Item -ItemType Junction -Path ".\dsh-plugin-text-translation\node_modules" `
>          -Target "$env:USERPROFILE\.dsh\profiles\demo\node_modules"
>
> # web profile 的依赖树在 DSH 安装锚点（npx 缓存）时，按包名逐项链接：
> New-Item -ItemType Junction -Path ".\dsh-plugin-text-translation\node_modules\@deepseek-ai" -Force
> New-Item -ItemType Junction -Path ".\dsh-plugin-text-translation\node_modules\@deepseek-ai\dsh-tools" `
>          -Target "$env:LOCALAPPDATA\npm-cache\_npx\<hash>\node_modules\@deepseek-ai\dsh-tools"
> # 同理链接 cordis、schemastery
> ```

### 方式四：`--patch` 覆盖层快速调试（不安装）

```bash
dsh --profile demo --patch ./dsh-plugin-text-translation/cordis.patch.yml
```

---

## ⚠️ 新 profile 初始化注意事项（实测经验）

1. **npm registry 的 `latest` tag 指错版本**：`@deepseek-ai/dsh-base` 的 `latest` 是旧版
   `0.0.1-rc.1`（其依赖 `dsh-fs-policy` 不存在于 registry），安装会失败。必须显式指定版本：
   ```bash
   dsh plugin --profile demo add @deepseek-ai/dsh-base@0.1.0-rc.6 @deepseek-ai/dsh-headless@0.1.0-rc.6
   ```
2. **pnpm 11 默认阻止依赖的 build scripts**：首次安装报 `ERR_PNPM_IGNORED_BUILDS` 时，
   把 profile 下 `pnpm-workspace.yaml` 中 `allowBuilds:` 段的 `set this to true or false`
   改为 `true`，再 `dsh plugin --profile demo install`。

---

## 🛠️ 注册的 DSH 工具 (Tools)

| 工具名称 | 说明 | 入参 |
| :--- | :--- | :--- |
| `extract_text` | 提取文件中的可翻译文本，应用标签遮罩并按行数切片；建议传 `output_json` 落盘避免大文本进入对话 | `input_file` (必需), `output_json`, `batch_size` |
| `assemble_text` | 将翻译结果还原标签后无损重组回原始格式文件 | `original_file` (必需), `translations_json` (必需), `output_file` (必需) |
| `inspect_text_file` | 轻量检查：格式、条目数、说话人、标签分布（不输出全文） | `file_path` (必需) |

---

## ⚙️ 插件配置项 (Config Schema)

在 profile 的 `cordis.patch.yml`（或 `--patch` 覆盖层）中可自定义：

```yaml
- insert:
    - id: text-translation
      name: dsh-plugin-text-translation
      config:
        pythonPath: python     # Python 解释器路径 (默认: python)
        batchSize: 25          # 单批次切片行数大小 (默认: 25)
```

---

## 🤖 推荐的翻译工作流（利用 DSH 子代理）

DSH 提供完整的子代理能力（`ctx.subagents` 服务 + 模型侧 `subagent` / `subagent_fork`
工具 + `workflow` 批量编排），Agent 可以这样编排一次翻译任务：

1. **摸底**：调用 `inspect_text_file` 了解格式、条目数与标签分布；
2. **提取**：调用 `extract_text`（传 `output_json` 保存分块 JSON）；
3. **并行翻译**：对每个批次分别启动一个子代理（`subagent`），或用一个
   `workflow` 脚本对全部批次做 fan-out 翻译，结果合并为一个 translations JSON；
   > 💡 **子代理结果去重**：实测中子代理完成通知可能重复投递，主 Agent 可能把
   > "重复通知"误当作新结果处理。建议在任务提示词中明确："子代理结果按 id 合并，
   > 已合并的 id 直接忽略重复通知"。
4. **回填**：调用 `assemble_text` 无损写回本地化文件。

---

## 🐍 Python 依赖

插件内置的 `python/local_helper.py` 需要：

- **必需**：`typer`、`pydantic`（`pip install typer pydantic`）
- **可选**（按需格式启用）：
  - XLSX → `openpyxl`
  - PDF → `PyMuPDF`
  - DOCX → `python-docx`
  - HTML → `beautifulsoup4`、`markdown2`

未安装可选依赖时，仅对应格式的提取会报错，其余功能不受影响。

---

## 🛠️ 开发

`dist/` 已提交到仓库（插件运行时加载 `dist/index.js`，clone 即用）。修改源码后重新构建：

```bash
npm install     # 安装 typescript 等开发依赖
npm run build   # tsc 编译到 dist/
```

### 测试

```bash
# Python 引擎冒烟测试（extract / inspect / assemble 无损断言）
pip install typer pydantic
python -m unittest discover -s test -v

# TypeScript 类型检查（需先 npm install）
npx tsc --noEmit
```

CI（GitHub Actions）会自动跑以上两项：`tsc --noEmit` 类型检查 + Python 3.11/3.13
矩阵冒烟测试。

### 同步上游引擎

`python/core/` 是 `multi_agent_translator` 引擎（非 LLM 部分）的随包快照。上游改动后运行：

```powershell
# 默认：只同步 core/（local_helper.py 保留插件定制：UTF-8 输出修复 + inspect 命令）
powershell -File scripts/sync-python-engine.ps1

# 同时覆盖 local_helper.py（CLI 层有冲突时需手动合并）
powershell -File scripts/sync-python-engine.ps1 -IncludeHelper

# 上游不在默认位置时指定路径
powershell -File scripts/sync-python-engine.ps1 -Source C:\path\to\multi_agent_translator
```

---

## 📄 License

MIT
