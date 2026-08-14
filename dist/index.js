/**
 * DeepSeek Harness (DSH) Plugin: Text & Document Localization
 *
 * 通用文本翻译插件：从游戏脚本与长文档中提取可翻译文本，对控制符/变量
 * (\c[1], \v[1], {0}, <color>, [ruby]) 做防爆遮罩，输出切片批次，
 * 并在翻译完成后无损回填组装。翻译本身由 DSH Agent 编排（可借助 DSH 的
 * subagent / workflow 能力并行处理各批次），本插件只提供提取与装配的原子能力。
 */
import { defineTool } from '@deepseek-ai/dsh-tools';
import Schema from '@deepseek-ai/schemastery';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
const execFileAsync = promisify(execFile);
export const name = 'text-translation';
export const inject = ['tools'];
export const Config = Schema.object({
    pythonPath: Schema.string().default('python').description('Python 解释器可执行路径'),
    batchSize: Schema.number().default(25).description('单批次切片行数大小'),
});
/** 提取/组装命令的默认超时（毫秒），大文件解析可能较慢。 */
const COMMAND_TIMEOUT_MS = 10 * 60 * 1000;
/** 检查命令的超时（毫秒）。 */
const INSPECT_TIMEOUT_MS = 5 * 60 * 1000;
/** 子进程 stdout 上限；超出时提示改用 output_json 落盘。 */
const MAX_BUFFER = 64 * 1024 * 1024;
/**
 * 定位随插件分发的 python/local_helper.py。
 * 在 apply 阶段解析一次：缺失即抛出清晰错误，避免每次工具调用都得到
 * 难以排查的 ENOENT。
 */
function locateHelperScript() {
    const currentDir = path.dirname(fileURLToPath(import.meta.url));
    const candidates = [
        // 打包布局：dist/ 或 src/ 的上一级 python/ 目录
        path.resolve(currentDir, '../python/local_helper.py'),
        path.resolve(currentDir, './python/local_helper.py'),
        // 兼容旧布局：与插件目录平级的 multi_agent_translator 工作区
        path.resolve(currentDir, '../../multi_agent_translator/local_helper.py'),
    ];
    const found = candidates.find((p) => fs.existsSync(p));
    if (!found) {
        throw new Error(`[text-translation] 未找到 python/local_helper.py（已检查: ${candidates.join(', ')}）。` +
            '请确认插件已完整安装（files 中应包含 python/ 目录）。');
    }
    return found;
}
function describeCommand(pythonBin, helperScript, args) {
    return [pythonBin, helperScript, ...args].join(' ');
}
function formatTail(buf, max = 2000) {
    if (!buf)
        return '';
    const text = Buffer.isBuffer(buf) ? buf.toString('utf-8') : buf;
    return text.length > max ? `…${text.slice(-max)}` : text;
}
function ensureFileExists(p, argName) {
    if (!fs.existsSync(p)) {
        throw new Error(`[text-translation] 参数 ${argName} 指向的文件不存在: ${p}`);
    }
}
/**
 * 执行 python helper 并严格解析其 stdout JSON。
 * 所有失败路径（找不到解释器、超时、非零退出、非 JSON 输出）都转为
 * 带有清晰上下文信息的错误，而不是把报错包装成"成功结果"返回给模型。
 */
async function runHelper(pythonBin, helperScript, args, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const command = describeCommand(pythonBin, helperScript, args);
    let stdout = '';
    try {
        try {
            const result = await execFileAsync(pythonBin, [helperScript, ...args], {
                encoding: 'utf-8',
                maxBuffer: MAX_BUFFER,
                signal: controller.signal,
            });
            stdout = result.stdout;
        }
        catch (err) {
            const e = err;
            if (e?.name === 'AbortError') {
                throw new Error(`[text-translation] 命令执行超时(${Math.round(timeoutMs / 1000)} 秒)，已终止子进程: ${command}`);
            }
            if (e?.code === 'ENOENT') {
                throw new Error(`[text-translation] 无法执行命令(ENOENT)，请检查 pythonPath 配置或 Python 是否已安装: ${command}`);
            }
            if (e?.code === 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER') {
                throw new Error(`[text-translation] 命令输出超过 ${MAX_BUFFER / 1024 / 1024}MB 上限，请为 extract_text 传入 output_json 将结果写入文件: ${command}`);
            }
            throw new Error(`[text-translation] 命令执行失败(退出码 ${e?.code ?? '未知'}): ${command}\n${formatTail(e?.stderr) || formatTail(e?.stdout)}`);
        }
        let data;
        try {
            data = JSON.parse(stdout.trim());
        }
        catch {
            throw new Error(`[text-translation] ${path.basename(helperScript)} 输出不是有效 JSON，前 500 字符:\n${stdout.slice(0, 500)}`);
        }
        if (typeof data !== 'object' || data === null || Array.isArray(data)) {
            throw new Error(`[text-translation] ${path.basename(helperScript)} 返回了意外的 JSON 结构: ${JSON.stringify(data).slice(0, 500)}`);
        }
        return data;
    }
    finally {
        clearTimeout(timer);
    }
}
export function apply(ctx, config) {
    const helperScript = locateHelperScript();
    // -------------------------------------------------------------
    // Tool 1: extract_text (提取 & 标签遮罩 & 切片)
    // -------------------------------------------------------------
    ctx.tools.register(defineTool({
        name: 'extract_text',
        description: '从游戏脚本或长文档(Mtool JSON, XLSX, CSV, RenPy, 字幕 SRT/VTT/ASS, PO, PDF, Word, Markdown, TXT)提取可翻译文本：对控制符与变量(\\c[1], {0}, <color>, [ruby])做防爆遮罩并按行数切片。' +
            '强烈建议传入 output_json 把完整分块结果写入文件，stdout 只返回摘要，避免大文本直接进入对话上下文。',
        parameters: {
            input_file: { type: 'string', required: true, description: '待翻译的源文件绝对路径' },
            output_json: { type: 'string', description: '可选：保存中间分块 JSON 的输出路径（建议提供）' },
            batch_size: { type: 'number', description: '每批次包含的文本行数，默认 25' },
        },
        output: {
            schema: { type: 'object', additionalProperties: true },
            render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
        },
        timeoutMs: COMMAND_TIMEOUT_MS,
        async execute(args) {
            ensureFileExists(args.input_file, 'input_file');
            const bSize = args.batch_size ?? config.batchSize ?? 25;
            const cmdArgs = ['extract', args.input_file, '--batch-size', String(bSize)];
            if (args.output_json) {
                cmdArgs.push('-o', args.output_json);
            }
            return await runHelper(config.pythonPath || 'python', helperScript, cmdArgs, COMMAND_TIMEOUT_MS);
        },
    }));
    // -------------------------------------------------------------
    // Tool 2: assemble_text (还原标签 & 无损重组)
    // -------------------------------------------------------------
    ctx.tools.register(defineTool({
        name: 'assemble_text',
        description: '把翻译审校完成的文本还原控制符与变量，100% 无损组装写回原始格式(JSON/XLSX/CSV/RPY/SRT/VTT/ASS/PO/PDF/DOCX/MD/TXT)，并报告已装配条目数。',
        parameters: {
            original_file: { type: 'string', required: true, description: '原始源文件路径' },
            translations_json: {
                type: 'string',
                required: true,
                description: '已翻译结果 JSON 文件的路径（支持 items 数组、batches 分块、id->text 字典等结构）',
            },
            output_file: { type: 'string', required: true, description: '最终输出的本地化文件路径' },
        },
        output: {
            schema: { type: 'object', additionalProperties: true },
            render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
        },
        timeoutMs: COMMAND_TIMEOUT_MS,
        async execute(args) {
            ensureFileExists(args.original_file, 'original_file');
            ensureFileExists(args.translations_json, 'translations_json');
            const cmdArgs = ['assemble', args.original_file, args.translations_json, args.output_file];
            return await runHelper(config.pythonPath || 'python', helperScript, cmdArgs, COMMAND_TIMEOUT_MS);
        },
    }));
    // -------------------------------------------------------------
    // Tool 3: inspect_text_file (轻量检查)
    // -------------------------------------------------------------
    ctx.tools.register(defineTool({
        name: 'inspect_text_file',
        description: '快速检查文本文件的格式、文本条目数、说话人列表及变量标签分布（轻量模式，不输出全文，适合翻译前摸底）。',
        parameters: {
            file_path: { type: 'string', required: true, description: '待检查的文件路径' },
        },
        output: {
            schema: { type: 'object', additionalProperties: true },
            render: (_args, value) => [{ type: 'text', text: JSON.stringify(value, null, 2) }],
        },
        timeoutMs: INSPECT_TIMEOUT_MS,
        async execute(args) {
            ensureFileExists(args.file_path, 'file_path');
            const cmdArgs = ['inspect', args.file_path];
            return await runHelper(config.pythonPath || 'python', helperScript, cmdArgs, INSPECT_TIMEOUT_MS);
        },
    }));
}
