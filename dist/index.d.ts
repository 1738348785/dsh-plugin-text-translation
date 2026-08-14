/**
 * DeepSeek Harness (DSH) Plugin: Text & Document Localization
 *
 * 通用文本翻译插件：从游戏脚本与长文档中提取可翻译文本，对控制符/变量
 * (\c[1], \v[1], {0}, <color>, [ruby]) 做防爆遮罩，输出切片批次，
 * 并在翻译完成后无损回填组装。翻译本身由 DSH Agent 编排（可借助 DSH 的
 * subagent / workflow 能力并行处理各批次），本插件只提供提取与装配的原子能力。
 */
import type { Context } from '@deepseek-ai/cordis';
import Schema from '@deepseek-ai/schemastery';
export declare const name = "text-translation";
export declare const inject: string[];
export interface Config {
    pythonPath?: string;
    batchSize?: number;
}
export declare const Config: Schema<Config>;
export declare function apply(ctx: Context, config: Config): void;
