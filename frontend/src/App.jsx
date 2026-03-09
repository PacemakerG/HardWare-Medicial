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
  onStartEcgFlow,
  isTyping,
  isEcgMonitoring,
  inputRef,
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
            title="ECG专家报告流程"
            onClick={onStartEcgFlow}
            disabled={isTyping || isEcgMonitoring}
          >
            <i className="fas fa-paperclip" />
          </button>
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

function ECGGuideModal({
  open,
  form,
  onChange,
  onClose,
  onSubmit,
  submitting,
}) {
  if (!open) return null;
  return (
    <div className="ecg-guide-backdrop" onClick={onClose}>
      <div className="ecg-guide-modal glass-effect" onClick={(e) => e.stopPropagation()}>
        <h3>ECG 专家报告引导</h3>
        <p>先补充基础信息。提交后会确认你是否已完成 ECG 采集并上传云端，确认后直接抓取最新一条数据生成报告。</p>
        <form onSubmit={onSubmit}>
          <div className="ecg-guide-grid">
            <label>
              姓名
              <input
                value={form.patientName}
                onChange={(e) => onChange('patientName', e.target.value)}
                required
              />
            </label>
            <label>
              年龄
              <input
                type="number"
                min="0"
                max="130"
                value={form.age}
                onChange={(e) => onChange('age', e.target.value)}
                required
              />
            </label>
            <label>
              性别
              <select
                value={form.gender}
                onChange={(e) => onChange('gender', e.target.value)}
                required
              >
                <option value="male">男</option>
                <option value="female">女</option>
                <option value="other">其他</option>
              </select>
            </label>
            <label>
              身高(cm)
              <input
                type="number"
                min="1"
                max="260"
                value={form.heightCm}
                onChange={(e) => onChange('heightCm', e.target.value)}
              />
            </label>
            <label>
              体重(kg)
              <input
                type="number"
                min="1"
                max="500"
                value={form.weightKg}
                onChange={(e) => onChange('weightKg', e.target.value)}
              />
            </label>
            <label>
              病历号(可选)
              <input
                value={form.patientId}
                onChange={(e) => onChange('patientId', e.target.value)}
              />
            </label>
          </div>
          <div className="ecg-guide-actions">
            <button type="button" className="action-btn" onClick={onClose} disabled={submitting}>
              取消
            </button>
            <button type="submit" className="action-btn" disabled={submitting}>
              {submitting ? '启动中...' : '开始制作报告'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LoginModal({
  open,
  form,
  onChange,
  onSubmit,
  submitting,
}) {
  if (!open) return null;
  return (
    <div className="ecg-guide-backdrop">
      <div className="ecg-guide-modal glass-effect">
        <h3>登录 MediGenius</h3>
        <p>请先登录，再开始使用聊天、画像记忆和 ECG 报告功能。</p>
        <form onSubmit={onSubmit}>
          <div className="ecg-guide-grid">
            <label>
              用户ID
              <input
                value={form.userId}
                onChange={(e) => onChange('userId', e.target.value)}
                placeholder="例如 doctor_zhang"
                required
              />
            </label>
            <label>
              租户ID
              <input
                value={form.tenantId}
                onChange={(e) => onChange('tenantId', e.target.value)}
                placeholder="default"
              />
            </label>
          </div>
          <div className="ecg-guide-actions">
            <button type="submit" className="action-btn" disabled={submitting}>
              {submitting ? '登录中...' : '登录并进入系统'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════
// SECTION 6 — APP ROOT  (all state + API logic)
// ══════════════════════════════════════════════════════════════
const API_BASE = '/api/v1';
const TENANT_STORAGE_KEY = 'medigenius_tenant_id';
const USER_STORAGE_KEY = 'medigenius_user_id';
const SESSION_STORAGE_KEY = 'medigenius_session_id';

function sanitizeIdentity(value, fallback) {
  const text = (value || '').trim();
  if (!text) return fallback;
  return text.replace(/[^a-zA-Z0-9_.:@/-]/g, '_').slice(0, 128) || fallback;
}

function createClientSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `sess-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function resolveClientIdentity() {
  if (typeof window === 'undefined') {
    return { tenantId: 'default', userId: 'anonymous' };
  }
  const query = new URLSearchParams(window.location.search);
  const tenantId = sanitizeIdentity(
    query.get('tenant') || localStorage.getItem(TENANT_STORAGE_KEY) || import.meta.env.VITE_TENANT_ID,
    'default',
  );
  const userId = sanitizeIdentity(
    query.get('user') || localStorage.getItem(USER_STORAGE_KEY) || import.meta.env.VITE_USER_ID,
    'anonymous',
  );
  localStorage.setItem(TENANT_STORAGE_KEY, tenantId);
  localStorage.setItem(USER_STORAGE_KEY, userId);
  return { tenantId, userId };
}

function resolveClientSessionId() {
  if (typeof window === 'undefined') return 'browser-session';
  const cached = localStorage.getItem(SESSION_STORAGE_KEY);
  if (cached && cached.trim()) return cached.trim();
  const generated = createClientSessionId();
  localStorage.setItem(SESSION_STORAGE_KEY, generated);
  return generated;
}

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
  const [identity, setIdentity] = useState(() => resolveClientIdentity());
  const [sessionHeaderId, setSessionHeaderId] = useState(() => resolveClientSessionId());
  const [authReady, setAuthReady] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false);
  const [loginForm, setLoginForm] = useState({
    userId: '',
    tenantId: resolveClientIdentity().tenantId,
  });
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
  const [inputValue, setInputValue] = useState('');
  const [showEcgGuide, setShowEcgGuide] = useState(false);
  const [isStartingEcg, setIsStartingEcg] = useState(false);
  const [isEcgMonitoring, setIsEcgMonitoring] = useState(false);
  const [ecgForm, setEcgForm] = useState({
    patientName: '',
    age: '',
    gender: 'male',
    heightCm: '',
    weightKg: '',
    patientId: '',
  });
  const [toast, setToast] = useState({ show: false, message: '', type: 'success' });

  const chatAreaRef = useRef(null);
  const inputRef = useRef(null);
  const ecgPollingRef = useRef(null);
  const ecgPollingSessionRef = useRef(null);
  const toastTimerRef = useRef(null);

  const persistSessionId = useCallback((sessionId) => {
    const normalized = (sessionId || '').trim();
    if (!normalized) return;
    setSessionHeaderId(normalized);
    localStorage.setItem(SESSION_STORAGE_KEY, normalized);
  }, []);

  const persistIdentity = useCallback((nextIdentity) => {
    const tenantId = sanitizeIdentity(nextIdentity?.tenantId, 'default');
    const userId = sanitizeIdentity(nextIdentity?.userId, 'anonymous');
    setIdentity({ tenantId, userId });
    localStorage.setItem(TENANT_STORAGE_KEY, tenantId);
    localStorage.setItem(USER_STORAGE_KEY, userId);
  }, []);

  const apiFetch = useCallback((path, options = {}, context = {}) => {
    const headers = new Headers(options.headers || {});
    headers.set('X-Tenant-ID', identity.tenantId);
    headers.set('X-User-ID', identity.userId);
    const effectiveSessionId = context.sessionId || currentSessionId || sessionHeaderId;
    if (effectiveSessionId) {
      headers.set('X-Session-ID', effectiveSessionId);
    }
    return fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  }, [identity.tenantId, identity.userId, currentSessionId, sessionHeaderId]);

  const onLoginFormChange = useCallback((key, value) => {
    setLoginForm(prev => ({ ...prev, [key]: value }));
  }, []);

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

  const stopEcgPolling = useCallback(() => {
    if (ecgPollingRef.current) {
      clearInterval(ecgPollingRef.current);
      ecgPollingRef.current = null;
    }
    ecgPollingSessionRef.current = null;
  }, []);

  useEffect(() => () => stopEcgPolling(), [stopEcgPolling]);

  // ── Auth bootstrap ────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const headers = {
          'X-Tenant-ID': identity.tenantId,
          'X-User-ID': identity.userId,
          'X-Session-ID': sessionHeaderId,
        };
        const res = await fetch(`${API_BASE}/auth/me`, { headers });
        const data = await res.json();
        if (cancelled) return;

        const nextIdentity = {
          tenantId: sanitizeIdentity(data?.tenant_id || identity.tenantId, 'default'),
          userId: sanitizeIdentity(data?.user_id || 'anonymous', 'anonymous'),
        };
        persistIdentity(nextIdentity);
        if (data?.session_id) persistSessionId(data.session_id);
        setIsLoggedIn(Boolean(data?.logged_in) && nextIdentity.userId !== 'anonymous');
      } catch {
        if (!cancelled) setIsLoggedIn(identity.userId !== 'anonymous');
      } finally {
        if (!cancelled) setAuthReady(true);
      }
    })();
    return () => { cancelled = true; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submitLogin = useCallback(async (e) => {
    e.preventDefault();
    if (isAuthSubmitting) return;
    const userId = sanitizeIdentity(loginForm.userId, '');
    const tenantId = sanitizeIdentity(loginForm.tenantId || identity.tenantId, 'default');
    if (!userId) {
      showToast('请输入用户ID', 'error');
      return;
    }

    setIsAuthSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionHeaderId,
        },
        body: JSON.stringify({ user_id: userId, tenant_id: tenantId }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        persistIdentity({ tenantId: data.tenant_id, userId: data.user_id });
        if (data.session_id) {
          persistSessionId(data.session_id);
          setCurrentSessionId(data.session_id);
        }
        setIsLoggedIn(true);
        setSessions(null);
        setMessages([]);
        setChatHistory([]);
        setShowWelcome(true);
        showToast(`已登录为 ${data.user_id}`, 'success');
      } else {
        showToast('登录失败，请重试', 'error');
      }
    } catch {
      showToast('登录请求失败', 'error');
    } finally {
      setIsAuthSubmitting(false);
    }
  }, [identity.tenantId, isAuthSubmitting, loginForm.tenantId, loginForm.userId, persistIdentity, persistSessionId, sessionHeaderId, showToast]);

  const logout = useCallback(async () => {
    try {
      await apiFetch('/auth/logout', { method: 'POST' });
    } catch {
      // ignore logout network failures, still clear local state
    }
    persistIdentity({ tenantId: identity.tenantId, userId: 'anonymous' });
    setIsLoggedIn(false);
    setCurrentSessionId(null);
    setMessages([]);
    setChatHistory([]);
    setSessions([]);
    setShowWelcome(true);
    showToast('已退出登录', 'info');
  }, [apiFetch, identity.tenantId, persistIdentity, showToast]);

  // ── Scroll to bottom ───────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    if (chatAreaRef.current) {
      chatAreaRef.current.scrollTo({ top: chatAreaRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, isTyping, scrollToBottom]);

  // ── Load sessions ──────────────────────────────────────────
  const loadSessions = useCallback(async () => {
    if (!isLoggedIn) {
      setSessions([]);
      return;
    }
    try {
      const res = await apiFetch('/sessions');
      const data = await res.json();
      if (data.success && data.sessions) setSessions(data.sessions);
    } catch {
      setSessions([]);
    }
  }, [apiFetch, isLoggedIn]);

  // ── Load current history on mount ──────────────────────────
  useEffect(() => {
    if (!authReady || !isLoggedIn) {
      setMessages([]);
      setChatHistory([]);
      setShowWelcome(true);
      return;
    }
    loadSessions();
    (async () => {
      try {
        const res = await apiFetch('/history');
        const data = await res.json();
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
        }
      } catch { /* silent */ }
    })();
  }, [apiFetch, authReady, isLoggedIn, loadSessions]);

  // ── Load session ───────────────────────────────────────────
  const loadSession = useCallback(async (sessionId) => {
    if (!isLoggedIn) return;
    try {
      const res = await apiFetch(`/session/${sessionId}`, {}, { sessionId });
      const data = await res.json();
      if (data.success) {
        setCurrentSessionId(sessionId);
        persistSessionId(sessionId);
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
  }, [apiFetch, isLoggedIn, persistSessionId, showToast]);

  // ── Delete session ─────────────────────────────────────────
  const deleteSession = useCallback(async (sessionId) => {
    if (!isLoggedIn) return;
    if (!window.confirm('Are you sure you want to delete this chat?')) return;
    try {
      const res = await apiFetch(`/session/${sessionId}`, { method: 'DELETE' }, { sessionId });
      if (res.ok) {
        await loadSessions();
        if (currentSessionId === sessionId) createNewChat();
        showToast('Chat deleted successfully', 'success');
      }
    } catch {
      showToast('Failed to delete chat', 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiFetch, currentSessionId, isLoggedIn, loadSessions, showToast]);

  // ── New chat ───────────────────────────────────────────────
  const createNewChat = useCallback(async () => {
    if (!isLoggedIn) return;
    try {
      const res = await apiFetch('/new-chat', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setMessages([]);
        setChatHistory([]);
        const nextSessionId = data?.session_id || createClientSessionId();
        setCurrentSessionId(nextSessionId);
        persistSessionId(nextSessionId);
        setShowWelcome(true);
        await loadSessions();
        showToast('New chat created', 'success');
      }
    } catch {
      showToast('Failed to create new chat', 'error');
    }
  }, [apiFetch, isLoggedIn, loadSessions, persistSessionId, showToast]);

  // ── Clear chat ─────────────────────────────────────────────
  const clearChat = useCallback(async () => {
    if (!isLoggedIn) return;
    if (!window.confirm('Are you sure you want to clear this conversation?')) return;
    try {
      const res = await apiFetch('/clear', { method: 'POST' });
      if (res.ok) {
        setMessages([]);
        setChatHistory([]);
        setShowWelcome(true);
        showToast('Conversation cleared', 'success');
      }
    } catch {
      showToast('Failed to clear conversation', 'error');
    }
  }, [apiFetch, isLoggedIn, showToast]);

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

  // ── ECG guided workflow ────────────────────────────────────
  const openEcgGuide = useCallback(() => {
    if (!isLoggedIn) {
      showToast('请先登录', 'info');
      return;
    }
    if (isTyping || isEcgMonitoring) {
      showToast('当前有进行中的任务，请稍后再试', 'info');
      return;
    }
    setShowEcgGuide(true);
  }, [isLoggedIn, isTyping, isEcgMonitoring, showToast]);

  const onEcgFormChange = useCallback((key, value) => {
    setEcgForm(prev => ({ ...prev, [key]: value }));
  }, []);

  const pollEcgTask = useCallback((taskId, sessionIdForTask) => {
    stopEcgPolling();
    setIsEcgMonitoring(true);
    ecgPollingSessionRef.current = sessionIdForTask || currentSessionId || sessionHeaderId;

    ecgPollingRef.current = setInterval(async () => {
      try {
        const res = await apiFetch(
          `/ecg/monitor/${taskId}`,
          {},
          { sessionId: ecgPollingSessionRef.current },
        );
        const data = await res.json();
        if (!res.ok) return;

        if (data.status === 'completed' && data.report) {
          stopEcgPolling();
          setIsEcgMonitoring(false);
          const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const alignedOutput = data.llm_output && typeof data.llm_output === 'object'
            ? data.llm_output
            : null;
          const reportContent = [
            alignedOutput?.report || data.report.report || '未返回报告内容',
            `风险等级：${data.report.risk_level || 'unknown'}`,
            `免责声明：${data.report.disclaimer || '本报告仅供参考。'}`,
            data.report.pdf_url ? `[下载PDF报告](${data.report.pdf_url})` : '',
          ].filter(Boolean).join('\n\n');
          const botMsg = {
            type: 'assistant',
            content: reportContent,
            timestamp: data.report.created_at || now,
            source: 'ECG Report Skill',
          };
          setMessages(prev => [...prev, botMsg]);
          setChatHistory(prev => [...prev, botMsg]);
          showToast('ECG 报告生成成功', 'success');
          loadSessions();
        } else if (data.status === 'failed') {
          stopEcgPolling();
          setIsEcgMonitoring(false);
          const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          const errMsg = {
            type: 'assistant',
            content: data.message || 'ECG 报告制作失败，请稍后重试。',
            timestamp: now,
            source: null,
          };
          setMessages(prev => [...prev, errMsg]);
          setChatHistory(prev => [...prev, errMsg]);
          showToast('ECG 报告制作失败', 'error');
        }
      } catch {
        // Keep polling on transient network errors.
      }
    }, 4000);
  }, [apiFetch, currentSessionId, loadSessions, sessionHeaderId, showToast, stopEcgPolling]);

  const submitEcgGuide = useCallback(async (e) => {
    e.preventDefault();
    if (!isLoggedIn) return;
    if (isStartingEcg) return;

    const patientName = ecgForm.patientName.trim();
    const age = Number(ecgForm.age);
    if (!patientName || !Number.isFinite(age)) {
      showToast('请完整填写姓名和年龄', 'error');
      return;
    }

    const payload = {
      patient_name: patientName,
      age,
      gender: ecgForm.gender,
      patient_id: ecgForm.patientId.trim() || null,
      height_cm: ecgForm.heightCm ? Number(ecgForm.heightCm) : null,
      weight_kg: ecgForm.weightKg ? Number(ecgForm.weightKg) : null,
    };

    const uploadConfirmed = window.confirm(
      '是否已采集 ECG 数据并上传云端？\n点击“确定”后将直接抓取网站最新一条数据生成 PDF 报告。',
    );
    if (!uploadConfirmed) {
      showToast('请先完成 ECG 采集并上传云端后再开始', 'info');
      return;
    }

    setIsStartingEcg(true);
    setShowEcgGuide(false);
    setShowWelcome(false);

    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg = {
      type: 'user',
      content: `ECG流程基础信息：姓名 ${patientName}，年龄 ${age}，性别 ${ecgForm.gender}`,
      timestamp: now,
      source: null,
    };
    setMessages(prev => [...prev, userMsg]);
    setChatHistory(prev => [...prev, userMsg]);

    try {
      const monitorSessionId = currentSessionId || sessionHeaderId || createClientSessionId();
      persistSessionId(monitorSessionId);
      const res = await apiFetch('/ecg/monitor/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }, { sessionId: monitorSessionId });
      const data = await res.json();
      if (res.ok && data.success && data.task_id) {
        const botMsg = {
          type: 'assistant',
          content: '已确认上传状态，正在直接抓取医生系统最新一条 ECG 数据，并生成 PDF 版专家报告。',
          timestamp: now,
          source: 'ECG Monitor',
        };
        setMessages(prev => [...prev, botMsg]);
        setChatHistory(prev => [...prev, botMsg]);
        pollEcgTask(data.task_id, monitorSessionId);
        showToast('已启动ECG报告制作任务', 'success');
      } else {
        const errText = (typeof data?.detail === 'string' && data.detail) || '启动ECG报告制作失败';
        const errMsg = { type: 'assistant', content: errText, timestamp: now, source: null };
        setMessages(prev => [...prev, errMsg]);
        setChatHistory(prev => [...prev, errMsg]);
        showToast('启动失败', 'error');
      }
    } catch {
      const errMsg = {
        type: 'assistant',
        content: '连接后端失败，无法启动 ECG 报告制作任务。',
        timestamp: now,
        source: null,
      };
      setMessages(prev => [...prev, errMsg]);
      setChatHistory(prev => [...prev, errMsg]);
      showToast('连接错误', 'error');
    } finally {
      setIsStartingEcg(false);
    }
  }, [apiFetch, currentSessionId, ecgForm, isLoggedIn, isStartingEcg, persistSessionId, pollEcgTask, sessionHeaderId, showToast]);

  // ── Send message ───────────────────────────────────────────
  const sendMessage = useCallback(async (overrideText) => {
    if (!isLoggedIn) {
      showToast('请先登录', 'info');
      return;
    }
    const message = (overrideText ?? inputValue).trim();
    if (!message || isTyping) return;

    setShowWelcome(false);
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg = { type: 'user', content: message, timestamp: time, source: null };
    setMessages(prev => [...prev, userMsg]);
    setChatHistory(prev => [...prev, userMsg]);
    setInputValue('');
    if (inputRef.current) { inputRef.current.style.height = 'auto'; }
    setIsTyping(true);

    try {
      const chatSessionId = currentSessionId || sessionHeaderId || createClientSessionId();
      persistSessionId(chatSessionId);
      const res = await apiFetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      }, { sessionId: chatSessionId });
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
  }, [apiFetch, currentSessionId, inputValue, isLoggedIn, isTyping, loadSessions, persistSessionId, sessionHeaderId, showToast]);

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
                <span>{isLoggedIn ? `AI Ready · ${identity.userId}` : '请先登录'}</span>
              </div>
            </div>
            <div className="header-actions">
              <button className="action-btn" title="Clear conversation" onClick={clearChat}>
                <i className="fas fa-trash" />
              </button>
              <button className="action-btn" title="Download chat" onClick={downloadChat}>
                <i className="fas fa-download" />
              </button>
              <button className="action-btn" title="Logout" onClick={logout}>
                <i className="fas fa-sign-out-alt" />
              </button>
            </div>
          </header>

          {/* Chat Area */}
          <ChatArea
            messages={messages}
            isTyping={isTyping}
            showWelcome={showWelcome}
            onQuickQuestion={handleQuickQuestion}
            chatAreaRef={chatAreaRef}
          />

          {/* Input Area */}
          <InputArea
            inputValue={inputValue}
            setInputValue={setInputValue}
            onSend={() => sendMessage()}
            onStartEcgFlow={openEcgGuide}
            isTyping={isTyping}
            isEcgMonitoring={isEcgMonitoring}
            inputRef={inputRef}
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

      <ECGGuideModal
        open={showEcgGuide}
        form={ecgForm}
        onChange={onEcgFormChange}
        onClose={() => setShowEcgGuide(false)}
        onSubmit={submitEcgGuide}
        submitting={isStartingEcg}
      />

      <LoginModal
        open={authReady && !isLoggedIn}
        form={loginForm}
        onChange={onLoginFormChange}
        onSubmit={submitLogin}
        submitting={isAuthSubmitting}
      />
    </>
  );
}
