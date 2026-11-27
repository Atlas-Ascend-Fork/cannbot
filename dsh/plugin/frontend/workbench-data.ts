// ----------------------------------------------------------------------------------------------------------
// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.
// ----------------------------------------------------------------------------------------------------------

/** Presentation copy only. Execution and initialization remain owned by the workflow packages. */
export const categories = ['全部', 'Ascend C'] as const
export type Category = typeof categories[number]
export interface WorkflowGuide { category: Category; icon: string; scenes: string[]; inputs: string[]; outputs: string[]; example: string }
export const guides: Record<string, WorkflowGuide> = {
  'ops-direct-invoke-flash': { category: 'Ascend C', icon: 'flash', scenes: ['快速实现与验证算子原型', '从明确的功能需求开始开发'], inputs: ['必需：算子功能及输入输出规格', '可选：参考代码、测试数据及目标硬件'], outputs: ['Ascend C 算子代码', '在可用环境中执行的编译与精度验证结果'], example: '帮我快速生成并验证一个 Ascend C 的 MatMul 算子，输入使用 float16，请先确认形状约束。' },
  'ops-direct-invoke': { category: 'Ascend C', icon: 'code', scenes: ['开发新的 Ascend C 算子', '通过直调方式集成算子'], inputs: ['必需：算子功能、输入输出及数据类型', '可选：参考实现、目标硬件及性能要求'], outputs: ['算子实现与直调示例', '按实际环境生成的验证结果及运行说明'], example: '请开发一个 Ascend C 的 Add 算子，输入为两个 float16 张量，并通过直调方式验证结果。' },
  'ops-registry-invoke': { category: 'Ascend C', icon: 'document', scenes: ['开发需要注册到框架的算子', '通过 ACLNN / GEIR 接入算子'], inputs: ['必需：算子定义、输入输出及接入方式', '可选：现有工程、参考实现及目标环境'], outputs: ['注册算子相关代码及接入示例', '按实际环境完成的验证与使用说明'], example: '开发一个 Ascend C 的自定义算子，并通过 ACLNN 接入。请先检查当前工程及输入输出定义。' },
}
export const guideFor = (id: string): WorkflowGuide => guides[id] ?? { category: 'Ascend C', icon: 'nodes', scenes: ['使用此工作流完成开发需求'], inputs: ['请描述目标，并提供相关工程或代码'], outputs: ['以工作流实际执行结果为准'], example: '请根据当前工程和我的需求开展工作，开始前先检查必要的输入。' }
export const cardOrder = Object.keys(guides)
const inputHints: Record<string, string> = {
  'ops-direct-invoke': '可补充算子功能、输入形状、数据类型和目标硬件。',
  'ops-direct-invoke-flash': '可补充输入形状、数据类型和目标硬件。',
  'ops-registry-invoke': '可补充输入输出规格，以及 ACLNN / GEIR 接入要求。',
}
export const inputHintFor = (id: string) => inputHints[id] ?? '可补充当前工程、相关代码和预期结果。'
