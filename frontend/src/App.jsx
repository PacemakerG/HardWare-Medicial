/**
 * MediGenius — Monolithic React App
 * Pixel-perfect mirror of templates/index.html + static/css/style.css + static/js/main.js
 *
 * Sections:
 *   1. Imports
 *   2. Utility helpers (formatTimeAgo, downloadChat)
 *   3. Sidebar component
 *   4. ChatArea component
 *   5. InputArea component
 *   6. App root (all state + API logic)
 */

// ══════════════════════════════════════════════════════════════
// SECTION 1 — IMPORTS
// ══════════════════════════════════════════════════════════════
import { useState, useEffect, useRef, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import './index.css';

// ══════════════════════════════════════════════════════════════
// SECTION 2 — UTILITY HELPERS
// ══════════════════════════════════════════════════════════════
function formatTimeAgo(timestamp) {
  const now = new Date();
  const past = new Date(timestamp);
  const diffMs = now - past;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return past.toLocaleDateString();
}

function buildDownloadText(chatHistory) {
  let content = 'MediGenius Chat Export\n';
  content += '='.repeat(50) + '\n\n';
  chatHistory.forEach((msg) => {
    content += `[${msg.timestamp}] ${msg.type === 'user' ? 'You' : 'MediGenius'}:\n`;
    content += msg.content + '\n';
    if (msg.source) content += `Source: ${msg.source}\n`;
    content += '\n';
  });
  return content;
}

function parseUploadedEcgPayload(rawText) {
  const text = (rawText || '').trim();
  if (!text) throw new Error('empty');

  // 1) Standard JSON object
  try {
    return JSON.parse(text);
  } catch {
    // continue
  }

  // 2) JSONL: parse first non-empty line
  const firstLine = text.split('\n').map(line => line.trim()).find(Boolean);
  if (!firstLine) throw new Error('empty');
  return JSON.parse(firstLine);
}

function buildFallbackWelcomeMessage() {
  const hour = new Date().getHours();
  const dayPart = hour < 11 ? '早上' : hour < 18 ? '下午' : '晚上';
  return `${dayPart}好，我是 MediGenius。你可以直接告诉我今天的症状、上传心电参数，或者继续跟进上一次的问题。你今天想先聊哪一项？`;
}

async function getGrantedGeolocation() {
  if (!navigator?.geolocation || !navigator?.permissions?.query) return null;

  try {
    const status = await navigator.permissions.query({ name: 'geolocation' });
    if (status.state !== 'granted') return null;

    return await new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (position) => resolve({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        }),
        () => resolve(null),
        {
          enableHighAccuracy: false,
          timeout: 1500,
          maximumAge: 10 * 60 * 1000,
        },
      );
    });
  } catch {
    return null;
  }
}

async function buildWelcomePayload() {
  const location = await getGrantedGeolocation();
  return {
    latitude: location?.latitude ?? null,
    longitude: location?.longitude ?? null,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    locale: navigator?.language || 'zh-CN',
  };
}

// ══════════════════════════════════════════════════════════════
// SECTION 3 — SIDEBAR COMPONENT
// ══════════════════════════════════════════════════════════════
function Sidebar({ sidebarOpen, sessions, currentSessionId, onNewChat, onLoadSession, onDeleteSession, onToggleTheme, theme }) {
  return (
    <aside className={`sidebar glass-effect${sidebarOpen ? '' : ' collapsed'}`}>
      <div className="sidebar-content">

        {/* Logo + New Chat */}
        <div className="sidebar-header">
          <div className="logo-wrapper">
            <div className="logo-animated">
              <div className="logo-pulse" />
              <i className="fas fa-heartbeat" />
            </div>
            <div className="logo-text">
              <h1>MediGenius</h1>
              <span className="version">AI Assistant v3.0</span>
            </div>
          </div>
          <button className="new-chat-btn" onClick={onNewChat}>
            <i className="fas fa-plus" />
            <span>New Chat</span>
          </button>
        </div>

        {/* Chat History */}
        <div className="chat-history-section">
          <div className="section-header">
            <span>Chat History</span>
            <div className="section-line" />
          </div>
          <div className="chat-list">
            {sessions === null ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
                <div className="loading-spinner" style={{ margin: '0 auto 10px' }} />
                Loading chats...
              </div>
            ) : sessions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
                No chat history yet
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.session_id}
                  className={`chat-item${currentSessionId === session.session_id ? ' active' : ''}`}
                  onClick={() => onLoadSession(session.session_id)}
                >
                  <i className="fas fa-message" />
                  <div className="chat-item-content">
                    <div className="chat-item-title">{session.preview || 'New conversation'}</div>
                    <div className="chat-item-time">{formatTimeAgo(session.last_active)}</div>
                  </div>
                  <button
                    className="chat-item-delete"
                    onClick={(e) => { e.stopPropagation(); onDeleteSession(session.session_id); }}
                  >
                    <i className="fas fa-trash" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Developer Info + Theme */}
        <div className="sidebar-footer">
          <div className="developer-card glass-effect">
            <div className="dev-header">
              <i className="fas fa-code" />
              <span>Developer</span>
            </div>
            <div className="dev-info">
              <p>Md. Emon Hasan</p>
              <div className="social-links">
                <a href="https://github.com/Md-Emon-Hasan" className="social-link" title="GitHub" target="_blank" rel="noreferrer">
                  <i className="fab fa-github" />
                </a>
                <a href="https://www.linkedin.com/in/md-emon-hasan-695483237/" className="social-link" title="LinkedIn" target="_blank" rel="noreferrer">
                  <i className="fab fa-linkedin" />
                </a>
                <a href="https://www.facebook.com/mdemon.hasan2001/" className="social-link" title="Facebook" target="_blank" rel="noreferrer">
                  <i className="fab fa-facebook" />
                </a>
                <a href="https://wa.me/8801834363533" className="social-link" title="WhatsApp" target="_blank" rel="noreferrer">
                  <i className="fab fa-whatsapp" />
                </a>
                <a href="mailto:emon.mlengineer@gmail.com" className="social-link" title="Email">
                  <i className="fas fa-envelope" />
                </a>
              </div>
            </div>
          </div>
          <button className="theme-btn glass-effect" onClick={onToggleTheme}>
            <i className={`fas ${theme === 'dark' ? 'fa-sun' : 'fa-moon'}`} />
          </button>
        </div>

      </div>
    </aside>
  );
}

// ══════════════════════════════════════════════════════════════
// SECTION 4 — CHAT AREA COMPONENT
// ══════════════════════════════════════════════════════════════
const QUICK_QUESTIONS = [
  { icon: 'fa-thermometer', label: 'Fever Symptoms', q: 'What are the symptoms of fever?' },
  { icon: 'fa-head-side-virus', label: 'Headache Treatment', q: 'How to treat a headache?' },
  { icon: 'fa-heart-pulse', label: 'High Blood Pressure', q: 'What causes high blood pressure?' },
  { icon: 'fa-notes-medical', label: 'Diabetes Management', q: 'Tell me about diabetes management' },
  { icon: 'fa-virus-covid', label: 'COVID Prevention', q: 'COVID-19 prevention tips' },
  { icon: 'fa-pills', label: 'Cold Remedies', q: 'Common cold remedies' },
];

function ChatArea({ messages, isTyping, showWelcome, onQuickQuestion, chatAreaRef }) {
  return (
    <div className="chat-area" ref={chatAreaRef}>

      {/* Welcome Screen */}
      <div className={`welcome-screen${showWelcome ? '' : ' hidden'}`}>
        <div className="welcome-content">
          <div className="logo-3d">
            <i className="fas fa-stethoscope" />
          </div>
          <h1 className="welcome-title">Welcome to MediGenius</h1>
          <p className="welcome-subtitle">Your AI-powered medical assistant is ready to help</p>

          <div className="quick-actions">
            <h3>Quick Questions:</h3>
            <div className="quick-buttons">
              {QUICK_QUESTIONS.map(({ icon, label, q }) => (
                <button key={q} className="quick-btn glass-effect" onClick={() => onQuickQuestion(q)}>
                  <i className={`fas ${icon}`} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="features">
            {[
              { icon: 'fa-brain', label: 'AI-Powered' },
              { icon: 'fa-database', label: 'Medical Database' },
              { icon: 'fa-shield-alt', label: 'Reliable Info' },
            ].map(({ icon, label }) => (
              <div key={label} className="feature-card glass-effect">
                <i className={`fas ${icon}`} />
                <span>{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="messages-container">
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} msg={msg} />
        ))}
      </div>

      {/* Typing Indicator */}
      <div className={`typing-indicator${isTyping ? ' active' : ''}`}>
        <div className="typing-bubble glass-effect">
          <div className="typing-content">
            <span className="typing-text">MediGenius is thinking</span>
            <div className="typing-dots">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}

function MessageBubble({ msg }) {
  const copyText = useCallback(() => {
    navigator.clipboard.writeText(msg.content).catch(() => { });
  }, [msg.content]);

  if (msg.type === 'user') {
    return (
      <div className="message user-message">
        <div className="message-wrapper">
          <div className="message-avatar"><i className="fas fa-user" /></div>
          <div className="message-content">
            <div className="message-text">
              {msg.content}
              <span className="message-time">{msg.timestamp}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="message bot-message">
      <div className="message-wrapper">
        <div className="message-avatar"><i className="fas fa-robot" /></div>
        <div className="message-content">
          <div className="message-text">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
          <span className="message-time">{msg.timestamp}</span>
          <div className="message-footer">
            {msg.source && (
              <span className="message-source">
                <i className="fas fa-database" />
                {msg.source}
              </span>
            )}
            <div className="message-actions">
              <button className="message-action" title="Copy" onClick={copyText}>
                <i className="fas fa-copy" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// SECTION 5 — INPUT AREA COMPONENT
// ══════════════════════════════════════════════════════════════
function InputArea({
  inputValue,
  setInputValue,
  onSend,
  isTyping,
  inputRef,
  uploadInputRef,
  onUploadFile,
}) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleInput = (e) => {
    setInputValue(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
  };

  return (
    <div className="input-area">
      <div className="input-wrapper">
        <div className="input-container glass-effect">
          <button
            className="input-btn"
            title="上传ECG参数JSON"
            onClick={() => uploadInputRef.current?.click()}
            disabled={isTyping}
          >
            <i className="fas fa-paperclip" />
          </button>
          <input
            ref={uploadInputRef}
            type="file"
            accept=".json,.jsonl,application/json,text/plain"
            style={{ display: 'none' }}
            onChange={onUploadFile}
          />
          <textarea
            ref={inputRef}
            className="message-input"
            placeholder="Ask your medical question..."
            rows={1}
            value={inputValue}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
          />
          <button className="input-btn" title="Voice input">
            <i className="fas fa-microphone" />
          </button>
          <button
            className="send-btn"
            title="Send message"
            aria-label="Send message"
            onClick={onSend}
            disabled={!inputValue.trim() || isTyping}
          >
            <i className="fas fa-paper-plane" />
          </button>
        </div>
        <div className="input-info">
          <i className="fas fa-info-circle" />
          <span>AI can make mistakes. Always consult healthcare professionals for medical advice.</span>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// SECTION 6 — APP ROOT  (all state + API logic)
// ══════════════════════════════════════════════════════════════
const API_BASE = '/api/v1';

// ── Mobile detection hook ──────────────────────────────────────
function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= breakpoint);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth <= breakpoint);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, [breakpoint]);
  return isMobile;
}

export default function App() {
  // ── State ──────────────────────────────────────────────────
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
  const isMobile = useIsMobile();
  // On mobile default to closed; on desktop restore from localStorage
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (window.innerWidth <= 768) return false;
    return localStorage.getItem('sidebarOpen') !== 'false';
  });
  const [sessions, setSessions] = useState(null);           // null = loading
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [chatHistory, setChatHistory] = useState([]);       // for download
  const [showWelcome, setShowWelcome] = useState(true);
  const [isTyping, setIsTyping] = useState(false);
  const [isWelcoming, setIsWelcoming] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [toast, setToast] = useState({ show: false, message: '', type: 'success' });

  const chatAreaRef = useRef(null);
  const inputRef = useRef(null);
  const uploadInputRef = useRef(null);
  const toastTimerRef = useRef(null);
  const bootstrappedRef = useRef(false);
  const hasUserActivityRef = useRef(false);

  // ── Theme ──────────────────────────────────────────────────
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
  }, [theme]);

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light');

  // ── Sidebar ────────────────────────────────────────────────
  const toggleSidebar = () => {
    setSidebarOpen(prev => {
      if (!isMobile) localStorage.setItem('sidebarOpen', !prev);
      return !prev;
    });
  };

  const closeSidebar = () => setSidebarOpen(false);

  // ── Toast ──────────────────────────────────────────────────
  const showToast = useCallback((message, type = 'success') => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ show: true, message, type });
    toastTimerRef.current = setTimeout(() => setToast(t => ({ ...t, show: false })), 3000);
  }, []);

  // ── Scroll to bottom ───────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTo({ top: chatAreaRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, isTyping, isWelcoming, scrollToBottom]);

  // ── Load sessions ──────────────────────────────────────────
  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      const data = await res.json();
      if (data.success && data.sessions) setSessions(data.sessions);
    } catch {
      setSessions([]);
    }
  }, []);

  const requestWelcomeMessage = useCallback(async () => {
    const fallbackContent = buildFallbackWelcomeMessage();
    setShowWelcome(false);
    setIsWelcoming(true);

    try {
      const payload = await buildWelcomePayload();
      const res = await fetch(`${API_BASE}/welcome`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!hasUserActivityRef.current && res.ok && data.success && data.response) {
        const botMsg = {
          type: 'assistant',
          content: data.response,
          timestamp: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          source: data.source || 'Welcome Concierge',
        };
        setCurrentSessionId(data.session_id || null);
        setMessages([botMsg]);
        setChatHistory([botMsg]);
        return true;
      }
    } catch {
      // Fall back to a local greeting below.
    } finally {
      setIsWelcoming(false);
    }

    if (hasUserActivityRef.current) return false;

    const fallbackMsg = {
      type: 'assistant',
      content: fallbackContent,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      source: 'Welcome Concierge',
    };
    setMessages([fallbackMsg]);
    setChatHistory([fallbackMsg]);
    return false;
  }, []);

  // ── Load current history on mount ──────────────────────────
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    (async () => {
      await loadSessions();
      try {
        const res = await fetch(`${API_BASE}/history`);
        const data = await res.json();
        if (data.session_id) setCurrentSessionId(data.session_id);
        if (data.success && data.messages && data.messages.length > 0) {
          const msgs = data.messages.map(m => ({
            type: m.role === 'user' ? 'user' : 'assistant',
            content: m.content,
            timestamp: m.timestamp || '',
            source: m.source || null,
          }));
          setMessages(msgs);
          setChatHistory(msgs.map(m => ({ ...m })));
          setShowWelcome(false);
        } else {
          await requestWelcomeMessage();
        }
      } catch {
        await requestWelcomeMessage();
      }
    })();
  }, [loadSessions, requestWelcomeMessage]);

  // ── Load session ───────────────────────────────────────────
  const loadSession = useCallback(async (sessionId) => {
    hasUserActivityRef.current = true;
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}`);
      const data = await res.json();
      if (data.success) {
        setCurrentSessionId(sessionId);
        const msgs = data.messages.map(m => ({
          type: m.role === 'user' ? 'user' : 'assistant',
          content: m.content,
          timestamp: m.timestamp || '',
          source: m.source || null,
        }));
        setMessages(msgs);
        setChatHistory(msgs.map(m => ({ ...m })));
        setShowWelcome(false);
        showToast('Chat loaded successfully', 'success');
      }
    } catch {
      showToast('Failed to load chat', 'error');
    }
  }, [showToast]);

  // ── Delete session ─────────────────────────────────────────
  const deleteSession = useCallback(async (sessionId) => {
    if (!window.confirm('Are you sure you want to delete this chat?')) return;
    try {
      const res = await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
      if (res.ok) {
        await loadSessions();
        if (currentSessionId === sessionId) createNewChat();
        showToast('Chat deleted successfully', 'success');
      }
    } catch {
      showToast('Failed to delete chat', 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId, loadSessions, showToast]);

  // ── New chat ───────────────────────────────────────────────
  const createNewChat = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/new-chat`, { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) {
        hasUserActivityRef.current = false;
        setMessages([]);
        setChatHistory([]);
        setCurrentSessionId(data.session_id || null);
        setShowWelcome(false);
        await loadSessions();
        await requestWelcomeMessage();
        showToast('New chat created', 'success');
      }
    } catch {
      showToast('Failed to create new chat', 'error');
    }
  }, [loadSessions, requestWelcomeMessage, showToast]);

  // ── Clear chat ─────────────────────────────────────────────
  const clearChat = useCallback(async () => {
    if (!window.confirm('Are you sure you want to clear this conversation?')) return;
    try {
      const res = await fetch(`${API_BASE}/clear`, { method: 'POST' });
      if (res.ok) {
        setMessages([]);
        setChatHistory([]);
        setShowWelcome(true);
        showToast('Conversation cleared', 'success');
      }
    } catch {
      showToast('Failed to clear conversation', 'error');
    }
  }, [showToast]);

  // ── Download chat ──────────────────────────────────────────
  const downloadChat = useCallback(() => {
    if (chatHistory.length === 0) { showToast('No messages to download', 'error'); return; }
    const content = buildDownloadText(chatHistory);
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `medigenius-chat-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Chat downloaded successfully', 'success');
  }, [chatHistory, showToast]);

  // ── ECG JSON upload -> report API ─────────────────────────
  const uploadEcgFile = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (isTyping) {
      showToast('请等待当前请求完成后再上传', 'info');
      return;
    }

    let payload;
    try {
      const text = await file.text();
      payload = parseUploadedEcgPayload(text);
    } catch {
      showToast('上传失败：文件不是有效 JSON/JSONL', 'error');
      return;
    }

    if (!payload || typeof payload !== 'object' || !payload.patient_info || !payload.features) {
      showToast('上传失败：缺少 patient_info 或 features 字段', 'error');
      return;
    }

    setShowWelcome(false);
    hasUserActivityRef.current = true;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg = {
      type: 'user',
      content: `已上传 ECG 参数文件：${file.name}`,
      timestamp: time,
      source: null,
    };
    setMessages(prev => [...prev, userMsg]);
    setChatHistory(prev => [...prev, userMsg]);
    setIsTyping(true);

    try {
      const res = await fetch(`${API_BASE}/ecg/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        const reportContent = [
          data.report || '未返回报告内容',
          `风险等级：${data.risk_level || 'unknown'}`,
          `免责声明：${data.disclaimer || '本报告仅供参考。'}`,
        ].join('\n\n');
        const botMsg = {
          type: 'assistant',
          content: reportContent,
          timestamp: data.created_at || time,
          source: 'ECG Report Skill',
        };
        setMessages(prev => [...prev, botMsg]);
        setChatHistory(prev => [...prev, botMsg]);
        showToast('ECG 报告生成成功', 'success');
        await loadSessions();
      } else {
        const errorText =
          (typeof data?.detail === 'string' && data.detail) ||
          'ECG 报告生成失败，请检查参数后重试';
        const errMsg = {
          type: 'assistant',
          content: errorText,
          timestamp: time,
          source: null,
        };
        setMessages(prev => [...prev, errMsg]);
        setChatHistory(prev => [...prev, errMsg]);
        showToast('ECG 报告生成失败', 'error');
      }
    } catch {
      const errMsg = {
        type: 'assistant',
        content: '连接后端失败，无法生成 ECG 报告，请稍后重试。',
        timestamp: time,
        source: null,
      };
      setMessages(prev => [...prev, errMsg]);
      setChatHistory(prev => [...prev, errMsg]);
      showToast('连接错误', 'error');
    } finally {
      setIsTyping(false);
    }
  }, [isTyping, loadSessions, showToast]);

  // ── Send message ───────────────────────────────────────────
  const sendMessage = useCallback(async (overrideText) => {
    const message = (overrideText ?? inputValue).trim();
    if (!message || isTyping) return;

    setShowWelcome(false);
    hasUserActivityRef.current = true;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg = { type: 'user', content: message, timestamp: time, source: null };
    setMessages(prev => [...prev, userMsg]);
    setChatHistory(prev => [...prev, userMsg]);
    setInputValue('');
    if (inputRef.current) { inputRef.current.style.height = 'auto'; }
    setIsTyping(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();

      if (data.success) {
        const botMsg = {
          type: 'assistant',
          content: data.response,
          timestamp: data.timestamp || time,
          source: data.source || null,
        };
        setMessages(prev => [...prev, botMsg]);
        setChatHistory(prev => [...prev, botMsg]);
        showToast('Response received', 'success');
        await loadSessions();
      } else {
        const errMsg = { type: 'assistant', content: 'Sorry, I encountered an error. Please try again.', timestamp: time, source: null };
        setMessages(prev => [...prev, errMsg]);
        showToast('Error occurred', 'error');
      }
    } catch {
      const errMsg = { type: 'assistant', content: 'Connection error. Please check your internet and try again.', timestamp: time, source: null };
      setMessages(prev => [...prev, errMsg]);
      showToast('Connection error', 'error');
    } finally {
      setIsTyping(false);
    }
  }, [inputValue, isTyping, loadSessions, showToast]);

  // Quick question handler
  const handleQuickQuestion = useCallback((q) => {
    setTimeout(() => sendMessage(q), 200);
  }, [sendMessage]);

  // ── Toast colors ───────────────────────────────────────────
  const toastColors = {
    success: 'linear-gradient(135deg, #10b981, #059669)',
    error: 'linear-gradient(135deg, #ef4444, #dc2626)',
    info: 'linear-gradient(135deg, #3b82f6, #2563eb)',
  };
  const toastIcons = {
    success: 'fa-check-circle',
    error: 'fa-exclamation-circle',
    info: 'fa-info-circle',
  };

  // ── Render ─────────────────────────────────────────────────
  return (
    <>
      {/* Animated Background */}
      <div className="animated-background">
        <div className="gradient-overlay" />
        <div className="floating-circles">
          <div className="circle circle-1" />
          <div className="circle circle-2" />
          <div className="circle circle-3" />
        </div>
      </div>

      <div className="app-container">

        {/* Sidebar Toggle */}
        <button className="sidebar-toggle-btn" onClick={toggleSidebar}>
          <i className="fas fa-bars" />
        </button>

        {/* Mobile backdrop — closes sidebar on click */}
        {isMobile && sidebarOpen && (
          <div className="sidebar-backdrop" onClick={closeSidebar} />
        )}

        {/* Sidebar */}
        <Sidebar
          sidebarOpen={sidebarOpen}
          sessions={sessions}
          currentSessionId={currentSessionId}
          onNewChat={createNewChat}
          onLoadSession={loadSession}
          onDeleteSession={deleteSession}
          onToggleTheme={toggleTheme}
          theme={theme}
        />

        {/* Main Content */}
        <main className={`main-content${sidebarOpen ? ' sidebar-open' : ''}`}>

          {/* Header */}
          <header className="app-header glass-header">
            <div className="header-content">
              <h2 className="gradient-text">Medical AI Assistant</h2>
              <div className="status-indicator">
                <div className="status-ring">
                  <span className="ring-pulse" />
                </div>
                <span>AI Ready</span>
              </div>
            </div>
            <div className="header-actions">
              <button className="action-btn" title="Clear conversation" onClick={clearChat}>
                <i className="fas fa-trash" />
              </button>
              <button className="action-btn" title="Download chat" onClick={downloadChat}>
                <i className="fas fa-download" />
              </button>
              <button className="action-btn" title="Settings">
                <i className="fas fa-cog" />
              </button>
            </div>
          </header>

          {/* Chat Area */}
          <ChatArea
            messages={messages}
            isTyping={isTyping || isWelcoming}
            showWelcome={showWelcome}
            onQuickQuestion={handleQuickQuestion}
            chatAreaRef={chatAreaRef}
          />

          {/* Input Area */}
          <InputArea
            inputValue={inputValue}
            setInputValue={setInputValue}
            onSend={() => sendMessage()}
            isTyping={isTyping}
            inputRef={inputRef}
            uploadInputRef={uploadInputRef}
            onUploadFile={uploadEcgFile}
          />

        </main>
      </div>

      {/* Toast Notification */}
      <div
        className={`toast${toast.show ? ' show' : ''}`}
        style={{ background: toastColors[toast.type] }}
      >
        <i className={`fas ${toastIcons[toast.type]}`} />
        <span>{toast.message}</span>
      </div>
    </>
  );
}
