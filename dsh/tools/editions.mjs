// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

/** Metadata shared by the compiler and the package builder. */
export const editions = {
  client: '@cannbot-plugin/cannbot-dsh',
  server: '@cannbot-plugin/cannbot-dsh-server',
}

export function editionManifest(source, edition, buildId) {
  const { scripts, devDependencies, ...manifest } = source
  const name = editions[edition]
  if (!name) throw new Error('Unknown CANNBot edition: ' + edition)
  return {
    ...manifest,
    name,
    cannbotEdition: edition,
    cannbotBuildId: buildId,
    ...(edition === 'server' ? {
      os: ['linux'],
      description: 'CANNBot development workbench for a Linux DSH server profile',
      files: manifest.files.filter(file => file !== 'remote'),
    } : {}),
  }
}
