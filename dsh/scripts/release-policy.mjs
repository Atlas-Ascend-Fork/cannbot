// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// This program is free software, you can redistribute it and/or modify it under the terms and conditions of
// CANN Open Software License Agreement Version 2.0 (the "License").
// Please refer to the License for details. You may not use this file except in compliance with the License.
// THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
// INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
// See LICENSE in the root of the software repository for the full text of the License.

import { readFile } from 'node:fs/promises'

export function validateReleasePolicy(policy, publicRelease = false) {
  if (!policy || !['development', 'public'].includes(policy.channel)) throw new Error('Invalid release channel')
  for (const name of ['userAgreementUrl', 'privacyPolicyUrl', 'hostSourceUrl', 'hostLicenseUrl', 'hostTermsUrl', 'hostPrivacyUrl']) {
    if (typeof policy[name] !== 'string') throw new Error(`Invalid ${name}`)
    if (!policy[name] && !publicRelease && policy.channel !== 'public' && ['userAgreementUrl', 'privacyPolicyUrl'].includes(name)) continue
    let url
    try { url = new URL(policy[name]) } catch { throw new Error(`Public release requires a legal-reviewed ${name}`) }
    if (url.protocol !== 'https:' || url.username || url.password || ['localhost', 'example.com', 'example.org'].includes(url.hostname)) throw new Error(`Invalid public HTTPS link: ${name}`)
  }
  return { ...policy, channel: publicRelease ? 'public' : policy.channel }
}
export async function readReleasePolicy(path, publicRelease = false) {
  return validateReleasePolicy(JSON.parse(await readFile(path, 'utf8')), publicRelease)
}
