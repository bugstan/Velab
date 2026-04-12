/**
 * 测试工具函数
 * 
 * 提供常用的测试辅助函数和自定义渲染器
 */

import { ReactElement } from 'react'
import { render, RenderOptions } from '@testing-library/react'

/**
 * 自定义渲染函数
 * 
 * 可以在这里添加全局的 Provider（如 Context、Router 等）
 */
export function renderWithProviders(
    ui: ReactElement,
    options?: Omit<RenderOptions, 'wrapper'>
) {
    return render(ui, { ...options })
}

// 重新导出所有 testing-library 的工具
export * from '@testing-library/react'
export { renderWithProviders as render }
