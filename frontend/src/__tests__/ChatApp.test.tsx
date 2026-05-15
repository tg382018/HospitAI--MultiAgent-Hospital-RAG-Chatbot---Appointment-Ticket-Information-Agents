import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatApp } from '../ChatApp';

// Mock the streamChat API so tests don't hit the network
vi.mock('../lib/api', () => ({
  streamChat: vi.fn(),
}));

import { streamChat } from '../lib/api';
const mockStreamChat = vi.mocked(streamChat);

// Suppress fetch errors from tenant-info fetch in component
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation((url: string) => {
      if (String(url).includes('chat-branding')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            header_background: 'linear-gradient(135deg, #0ea5e9 0%, #0891b2 50%, #14b8a6 100%)',
            welcome_title: 'Merhaba! 👋',
            welcome_subtitle:
              'Size nasıl yardımcı olabilirim? Randevu almak, randevularınızı sorgulamak veya bir şikayetinizi iletmek için aşağıdan başlayabilirsiniz.',
            logo_url: null,
            favicon_url: null,
            quick_actions: [
              { icon: '📅', label: 'Randevu Al' },
              { icon: '📋', label: 'Randevularım' },
              { icon: '💬', label: 'Şikayet Bildir' },
              { icon: '❓', label: 'Hastane Bilgisi' },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    })
  );
  sessionStorage.clear();
});

describe('ChatApp', () => {
  it('renders welcome state when no messages', () => {
    render(<ChatApp />);
    expect(screen.getByText('Merhaba! 👋')).toBeInTheDocument();
  });

  it('renders quick-chip buttons', () => {
    render(<ChatApp />);
    expect(screen.getByText('Randevu Al')).toBeInTheDocument();
    expect(screen.getByText('Randevularım')).toBeInTheDocument();
    expect(screen.getByText('Şikayet Bildir')).toBeInTheDocument();
    expect(screen.getByText('Hastane Bilgisi')).toBeInTheDocument();
  });

  it('send button is disabled when input is empty', () => {
    render(<ChatApp />);
    // The submit button should be the one inside the form; check disabled state via aria
    const form = document.querySelector('form')!;
    const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(true);
  });

  it('send button becomes enabled when text is entered', async () => {
    const user = userEvent.setup();
    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'Randevu almak istiyorum');
    const form = document.querySelector('form')!;
    const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn.disabled).toBe(false);
  });

  it('shows user message after send', async () => {
    const user = userEvent.setup();
    mockStreamChat.mockImplementation(async (_path, _init, handlers) => {
      handlers.onMeta?.({ conversation_id: 'conv-123' });
      handlers.onFinal?.({
        message: 'Yardımcı olabilirim.',
        intent: 'general',
        sources: [],
        rag_used: false,
        escalated: false,
        safety_flag: false,
        safety_reason: '',
      });
    });

    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'Merhaba');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(screen.getByText('Merhaba')).toBeInTheDocument();
    });
  });

  it('shows assistant response after stream completes', async () => {
    const user = userEvent.setup();
    mockStreamChat.mockImplementation(async (_path, _init, handlers) => {
      handlers.onMeta?.({ conversation_id: 'conv-456' });
      handlers.onToken?.('Yardımcı ');
      handlers.onToken?.('olabilirim.');
      handlers.onFinal?.({
        message: 'Yardımcı olabilirim.',
        intent: 'general',
        sources: [],
        rag_used: false,
        escalated: false,
        safety_flag: false,
        safety_reason: '',
      });
    });

    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'Merhaba');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(screen.getByText('Yardımcı olabilirim.')).toBeInTheDocument();
    });
  });

  it('shows error banner when stream fails', async () => {
    const user = userEvent.setup();
    mockStreamChat.mockRejectedValue(new Error('Bağlantı hatası'));

    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'test');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(screen.getByText('Bağlantı hatası')).toBeInTheDocument();
    });
  });

  it('clears messages when new chat button is clicked', async () => {
    const user = userEvent.setup();
    mockStreamChat.mockImplementation(async (_path, _init, handlers) => {
      handlers.onMeta?.({ conversation_id: 'conv-789' });
      handlers.onFinal?.({
        message: 'Evet.',
        intent: 'general',
        sources: [],
        rag_used: false,
        escalated: false,
        safety_flag: false,
        safety_reason: '',
      });
    });

    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'test');
    await user.keyboard('{Enter}');

    await waitFor(() => screen.getByText('test'));

    const clearBtn = screen.getByTitle('Yeni konuşma başlat');
    await user.click(clearBtn);

    // After clear, welcome screen should reappear
    expect(screen.getByText('Merhaba! 👋')).toBeInTheDocument();
  });

  it('stores conversation_id in sessionStorage after first message', async () => {
    const user = userEvent.setup();
    mockStreamChat.mockImplementation(async (_path, _init, handlers) => {
      handlers.onMeta?.({ conversation_id: 'conv-stored' });
      handlers.onFinal?.({
        message: 'Ok.',
        intent: 'general',
        sources: [],
        rag_used: false,
        escalated: false,
        safety_flag: false,
        safety_reason: '',
      });
    });

    render(<ChatApp />);
    const textarea = screen.getByPlaceholderText(/Mesajınızı yazın/);
    await user.type(textarea, 'hi');
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(sessionStorage.getItem('hospitai-chat-conversation-id')).toBe('conv-stored');
    });
  });
});
