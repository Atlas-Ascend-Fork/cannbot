#!/usr/bin/env node
import { main } from '../lib/installer.mjs'
main().catch(error => { console.error(`\n操作未完成：${error.message}`); process.exitCode = 1 })
