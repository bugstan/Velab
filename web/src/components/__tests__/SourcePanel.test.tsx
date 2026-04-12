import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SourcePanel from '../SourcePanel';
import { SourceReference } from '@/lib/types';

describe('SourcePanel Component', () => {
  const mockSources: SourceReference[] = [
    { title: 'Log File A', type: 'log' },
    { title: 'Jira-123', type: 'jira', url: 'https://jira.com/123' },
    { title: 'Tech Doc', type: 'document' },
    { title: 'User Manual', type: 'pdf' },
  ];

  it('renders correctly when sources are provided', () => {
    render(<SourcePanel sources={mockSources} />);
    
    expect(screen.getByText(/证据来源 \(4\)/)).toBeInTheDocument();
    expect(screen.getByText('Log File A')).toBeInTheDocument();
    expect(screen.getByText('Jira-123')).toBeInTheDocument();
    expect(screen.getByText('Tech Doc')).toBeInTheDocument();
    expect(screen.getByText('User Manual')).toBeInTheDocument();
  });

  it('returns null when sources list is empty', () => {
    const { container } = render(<SourcePanel sources={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('opens URL in new tab when a source with url is clicked', () => {
    const windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    render(<SourcePanel sources={mockSources} />);
    
    const jiraButton = screen.getByText('Jira-123').closest('button');
    if (jiraButton) fireEvent.click(jiraButton);
    
    expect(windowOpenSpy).toHaveBeenCalledWith('https://jira.com/123', '_blank');
    windowOpenSpy.mockRestore();
  });

  it('opens detail modal when a source without url is clicked', () => {
    render(<SourcePanel sources={mockSources} />);
    
    const logButton = screen.getByText('Log File A').closest('button');
    if (logButton) fireEvent.click(logButton);
    
    expect(screen.getByText('此来源暂无详细内容预览。')).toBeInTheDocument();
    expect(screen.getByText('日志')).toBeInTheDocument();
  });

  it('closes detail modal when close button is clicked', () => {
    render(<SourcePanel sources={mockSources} />);
    
    const logButton = screen.getByText('Log File A').closest('button');
    if (logButton) fireEvent.click(logButton);
    
    const closeButton = screen.getByRole('button', { name: '' }); // The SVG close button
    fireEvent.click(closeButton);
    
    expect(screen.queryByText('此来源暂无详细内容预览。')).not.toBeInTheDocument();
  });

  it('closes detail modal when clicking outside', async () => {
    render(<SourcePanel sources={mockSources} />);
    
    const logButton = screen.getByText('Log File A').closest('button');
    if (logButton) fireEvent.click(logButton!);
    
    // Modal should be open
    expect(screen.getByText('此来源暂无详细内容预览。')).toBeInTheDocument();

    const overlay = screen.getByTestId('modal-overlay');
    fireEvent.click(overlay);
    
    await waitFor(() => {
      expect(screen.queryByText('此来源暂无详细内容预览。')).not.toBeInTheDocument();
    });
  });

  it('displays correct icon and label for each source type', () => {
    // Test all types in a single render to hit more lines
    render(<SourcePanel sources={mockSources} />);
    
    // Check icons exist
    expect(screen.getByText('📄')).toBeInTheDocument();
    expect(screen.getByText('🎫')).toBeInTheDocument();
    expect(screen.getByText('📚')).toBeInTheDocument();
    expect(screen.getByText('📑')).toBeInTheDocument();
    
    // Click each and check labels
    const labels = ['日志', 'Jira工单', '技术文档', 'PDF文档'];
    const titles = ['Log File A', 'Jira-123', 'Tech Doc', 'User Manual'];
    
    titles.forEach((title, index) => {
        // Skip Jira-123 as it matches window.open
        if (title === 'Jira-123') return;

        const btn = screen.getByText(title).closest('button');
        if (btn) fireEvent.click(btn);
        expect(screen.getByText(labels[index])).toBeInTheDocument();
        
        // Close modal
        const closeBtn = screen.getByTestId('modal-overlay');
        fireEvent.click(closeBtn);
    });
  });

  it('displays default icon and label for unknown source type', () => {
    // @ts-ignore
    const unknownSource: SourceReference = { title: 'Unknown', type: 'unknown' };
    render(<SourcePanel sources={[unknownSource]} />);
    
    expect(screen.getByText('📌')).toBeInTheDocument();
    
    const btn = screen.getByText('Unknown').closest('button');
    if (btn) fireEvent.click(btn);
    expect(screen.getByText('来源')).toBeInTheDocument();
  });
});
