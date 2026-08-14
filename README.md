# 📖 dsh-plugin-text-translation

> **DeepSeek Harness (DSH) 文本与文档翻译插件**（遵循 DSH 插件规范，非官方插件）。
> 为 DSH Agent 提供**标签防爆遮罩**、**多格式文本提取/切片**与**无损回填组装**能力，
> 覆盖游戏脚本与长文档两类场景。翻译本身由 DSH Agent 编排完成——可借助 DSH 内置的
> `subagent` / `subagent_fork` / `workflow` 工具并行翻译各批次，本插件只负责
> "提取"与"装配"这两个原子环节。

---

## 🌟 核心特性

- 🛡️ **标签防爆遮罩 (Tag Protector)**：自动识别并保护 RPG Maker (`\c[1]`, `\v[1]`, `\n`)、
  Unity/RichText (`<color>`, `<b>`)、变量占位符 (`{player}`, `{0}`, `%s`) 与 Ren'Py 标签，
  翻译后 **100% 精确无损还原**。
- 📑 **全格式支持**：
  - **游戏脚本**：Mtool JSON (`ManualTransFile.json`)、Translator++ 表格 (XLSX/CSV)、
    Ren'Py (`.rpy`)、字幕 (SRT/ASS/VTT)、Gettext (`.po`)。
  - **长文档**：PDF、Word (`.docx`)、Markdown、HTML、TXT。
- 🧩 **DSH 规范插件**：
  - 导出标准的 `dsh.bundle` Manifest（`dsh.bundle.patch`），随 `dsh plugin` 安装后自动加入
    profile 的 bundle 层。
  - 注册 `extract_text`、`assemble_text`、`inspect_text_file` 三个工具供 DSH Agent 调度。
  - Python 引擎（`python/` 目录）随插件一起分发，安装即用，无外部路径依赖。

---

## 📦 安装与使用

### 方式一：安装到指定的 DSH Profile (推荐)

在您的 DeepSeek Harness 工程目录下运行：

```bash
dsh plugin --profile demo add ./dsh-plugin-text-translation
```

`dsh` 会自动将插件的 `cordis.patch.yml` 追加进 profile 的 bundle 层。

> ⚠️ **本地源码安装注意事项**：pnpm 对本地路径包使用符号链接（junction），而 Node ESM
> 会按符号链接的**真实路径**解析依赖——插件代码 `import '@deepseek-ai/dsh-tools'` 时会从
> 插件源码目录向上查找，找不到 profile 里的依赖包并报 `ERR_MODULE_NOT_FOUND`。
> 解决办法（Windows 示例）：把 profile 的依赖树以 junction 暴露给插件目录，一次即可：
>
> ```powershell
> New-Item -ItemType Junction -Path ".\dsh-plugin-text-translation\node_modules" `
>          -Target "$env:USERPROFILE\.dsh\profiles\demo\node_modules"
> ```
>
> 发布到 npm registry 后安装（真实解压到 pnpm store）则无此问题。

### 方式二：使用 `--patch` 覆盖层快速调试

```bash
dsh --profile demo --patch ./dsh-plugin-text-translation/cordis.patch.yml
```

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

```bash
npm install     # 安装 typescript 等开发依赖
npm run build   # tsc 编译到 dist/
```

---

## 📄 License

MIT
