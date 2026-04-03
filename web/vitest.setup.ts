import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { server } from './src/__tests__/mocks/server';

// Mock scrollIntoView
Element.prototype.scrollIntoView = () => { };

// 启动 MSW 服务器
beforeAll(() => {
    server.listen({ onUnhandledRequest: 'error' });
});

// 每个测试后重置处理器
afterEach(() => {
    cleanup();
    server.resetHandlers();
});

// 测试完成后关闭服务器
afterAll(() => {
    server.close();
});
