/**
 * MSW 服务器设置
 * 
 * 为测试环境配置 Mock Service Worker
 */

import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// 创建 MSW 服务器实例
export const server = setupServer(...handlers)
