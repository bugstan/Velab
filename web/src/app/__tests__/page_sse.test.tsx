import { render, screen, waitFor } from '@/__tests__/utils/test-utils'
import Home from '@/app/page'
import userEvent from '@testing-library/user-event'
import { vi, describe, it, beforeEach, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '@/__tests__/mocks/server'

describe('Home Page SSE Events Tests', { timeout: 30000 }, () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    /** Helper to create SSE stream responses with MSW */
    function createSseResponse(lines: string[]) {
        const encoder = new TextEncoder()
        const stream = new ReadableStream({
            start(controller) {
                lines.forEach(line => {
                    controller.enqueue(encoder.encode(line))
                })
                controller.close()
            }
        })
        return new HttpResponse(stream, {
            headers: { 'Content-Type': 'text/event-stream' }
        })
    }

    it('should handle complex SSE event sequence', async () => {
        const user = userEvent.setup()

        const events = [
            'data: {"type":"step_start","step":{"stepNumber":1,"agentName":"Orchestrator","status":"running","statusText":"Thinking..."}}\n\n',
            'data: {"type":"step_complete","step":{"stepNumber":1,"agentName":"Orchestrator","status":"completed","statusText":"Done","result":"Plan: A"}}\n\n',
            'data: {"type":"step_start","step":{"stepNumber":2,"agentName":"Log Agent","status":"running","statusText":"Analyzing..."}}\n\n',
            'data: {"type":"step_progress","stepNumber":2,"partialResult":"Searching logs..."}\n\n',
            'data: {"type":"workspace_update","agent":"Log Agent","file":"todo.md","change":"[x] Scan logs"}\n\n',
            'data: {"type":"step_complete","step":{"stepNumber":2,"agentName":"Log Agent","status":"completed","statusText":"Done","result":"Found error 404"}}\n\n',
            'data: {"type":"content_delta","content":"Based "}\n\n',
            'data: {"type":"content_delta","content":"on "}\n\n',
            'data: {"type":"content_delta","content":"analysis."}\n\n',
            'data: {"type":"content_complete","sources":[{"title":"log.txt","type":"log"}],"confidenceLevel":"high"}\n\n',
            'data: {"type":"done"}\n\n'
        ]

        server.use(
            http.post('/api/chat', () => createSseResponse(events))
        )

        render(<Home />)

        const input = screen.getByPlaceholderText('Ask a question')
        await user.type(input, 'Analyze logs{Enter}')

        // Wait for final content
        expect(await screen.findByText(/Based on analysis/, {}, { timeout: 15000 })).toBeInTheDocument()

        // Expand the thinking process
        const thinkingButton = await screen.findByText(/Thinking process/)
        await user.click(thinkingButton)

        // Check if steps were rendered
        expect(screen.getByText('Orchestrator')).toBeInTheDocument()
        expect(screen.getByText('Log Agent')).toBeInTheDocument()

        // Check for sources
        expect(screen.getByText('证据来源 (1)')).toBeInTheDocument()
        expect(screen.getByText('log.txt')).toBeInTheDocument()
    })

})

