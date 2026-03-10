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

  if (diffMins < 1) return '刚刚';
  if (diffMins < 60) return `${diffMins} 分钟前`;
  if (diffHours < 24) return `${diffHours} 小时前`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return past.toLocaleDateString();
}

function buildDownloadText(chatHistory) {
  let content = '医枢智疗 对话导出\n';
  content += '='.repeat(50) + '\n\n';
  chatHistory.forEach((msg) => {
    content += `[${msg.timestamp}] ${msg.type === 'user' ? '用户' : '医枢智疗'}:\n`;
    content += msg.content + '\n';
    if (msg.source) content += `来源: ${msg.source}\n`;
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
              <h1>医枢智疗</h1>
              <span className="version">临床智能协同平台 v4.0</span>
            </div>
          </div>
          <button className="new-chat-btn" onClick={onNewChat}>
            <i className="fas fa-plus" />
            <span>新建会话</span>
          </button>
        </div>

        {/* Chat History */}
        <div className="chat-history-section">
          <div className="section-header">
            <span>会话历史</span>
            <div className="section-line" />
          </div>
          <div className="chat-list">
            {sessions === null ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
                <div className="loading-spinner" style={{ margin: '0 auto 8px' }} />
                加载中...
              </div>
            ) : sessions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
                暂无历史会话
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
                    <div className="chat-item-title">{session.preview || '新会话'}</div>
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
              <span>联合开发</span>
            </div>
            <div className="dev-info">
              <p>
                <a
                  href="https://github.com/PacemakerG/HardWare-Medicial"
                  className="dev-name-link"
                  title="elonge GitHub"
                  target="_blank"
                  rel="noreferrer"
                >
                  elonge
                </a>
              </p>
              <p>
                <a
                  href="https://github.com/xhforever/HardWare-Medicial"
                  className="dev-name-link"
                  title="xhforever GitHub"
                  target="_blank"
                  rel="noreferrer"
                >
                  xhforever
                </a>
              </p>
              <div className="social-links">
                <a href="https://github.com/PacemakerG/HardWare-Medicial" className="social-link" title="elonge GitHub" target="_blank" rel="noreferrer">
                  <i className="fab fa-github" />
                </a>
                <a href="https://github.com/xhforever/HardWare-Medicial" className="social-link" title="xhforever GitHub" target="_blank" rel="noreferrer">
                  <i className="fab fa-github" />
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
const DEPARTMENT_OPTIONS = [
  { code: 'general_medical', label: '通用医疗', zh: '通用医疗', icon: 'fa-house-medical' },
  { code: 'general_surgery', label: '普外科', zh: '普外科', icon: 'fa-user-doctor' },
  { code: 'pediatrics', label: '儿科', zh: '儿科', icon: 'fa-baby' },
  { code: 'neurology', label: '神经内科', zh: '神经内科', icon: 'fa-brain' },
  { code: 'infectious_disease', label: '感染科', zh: '感染科', icon: 'fa-virus' },
  { code: 'ent', label: '耳鼻喉科', zh: '耳鼻喉科', icon: 'fa-ear-listen' },
  { code: 'ophthalmology', label: '眼科', zh: '眼科', icon: 'fa-eye' },
  { code: 'dermatology', label: '皮肤科', zh: '皮肤科', icon: 'fa-hand-dots' },
];

function ChatArea({
  messages,
  isTyping,
  showWelcome,
  onSelectDepartment,
  onClearDepartment,
  selectedDepartment,
  chatAreaRef,
}) {
  return (
    <div className="chat-area" ref={chatAreaRef}>

      {/* Welcome Screen */}
      <div className={`welcome-screen${showWelcome ? '' : ' hidden'}`}>
        <div className="welcome-content">
          <div className="logo-3d">
            <i className="fas fa-stethoscope" />
          </div>
          <h1 className="welcome-title">欢迎使用 医枢智疗</h1>
          <p className="welcome-subtitle">面向多科室问诊与 ECG 报告的一体化医疗智能工作台</p>

          <div className="quick-actions">
            <h3>专业科室选择：</h3>
            <div className="quick-buttons">
              {DEPARTMENT_OPTIONS.map(({ code, label, zh, icon }) => (
                <button
                  key={code}
                  className="quick-btn glass-effect"
                  onClick={() => onSelectDepartment(code)}
                  style={{
                    border: selectedDepartment === code ? '1px solid var(--accent)' : undefined,
                    boxShadow: selectedDepartment === code ? '0 0 0 3px var(--accent-glow)' : undefined,
                  }}
                >
                  <i className={`fas ${icon}`} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
            <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-secondary)' }}>
              当前模式：
              {selectedDepartment ? ` 锁定 ${DEPARTMENT_OPTIONS.find(item => item.code === selectedDepartment)?.zh || selectedDepartment}` : ' 自动路由'}
              <button
                className="message-action"
                style={{ marginLeft: 10 }}
                onClick={onClearDepartment}
              >
                清除选择
              </button>
            </div>
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
            <span className="typing-text">医枢智疗正在生成答案</span>
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
              <button className="message-action" title="复制" onClick={copyText}>
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
            placeholder="请输入你的问题（可直接描述症状、病史或检查结果）"
            rows={1}
            value={inputValue}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
          />
          <button className="input-btn" title="语音输入">
            <i className="fas fa-microphone" />
          </button>
          <button
            className="send-btn"
            title="发送消息"
            aria-label="发送消息"
            onClick={onSend}
            disabled={!inputValue.trim() || isTyping}
          >
            <i className="fas fa-paper-plane" />
          </button>
        </div>
        <div className="input-info">
          <i className="fas fa-info-circle" />
          <span>本系统为辅助决策工具，不能替代医生面诊。</span>
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
        <p>先补充基础信息。提交后系统将按后端配置的数据模式生成 ECG 报告。</p>
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
        <h3>登录 医枢智疗</h3>
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
  const [selectedDepartment, setSelectedDepartment] = useState(null);
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
  const ecgEventSourceRef = useRef(null);
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
    if (ecgEventSourceRef.current) {
      ecgEventSourceRef.current.close();
      ecgEventSourceRef.current = null;
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
        setSelectedDepartment(null);
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
    setSelectedDepartment(null);
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
        showToast('会话加载成功', 'success');
      }
    } catch {
      showToast('会话加载失败', 'error');
    }
  }, [apiFetch, isLoggedIn, persistSessionId, showToast]);

  // ── Delete session ─────────────────────────────────────────
  const deleteSession = useCallback(async (sessionId) => {
    if (!isLoggedIn) return;
    if (!window.confirm('确认删除该会话？')) return;
    try {
      const res = await apiFetch(`/session/${sessionId}`, { method: 'DELETE' }, { sessionId });
      if (res.ok) {
        await loadSessions();
        if (currentSessionId === sessionId) createNewChat();
        showToast('会话删除成功', 'success');
      }
    } catch {
      showToast('会话删除失败', 'error');
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
        setSelectedDepartment(null);
        await loadSessions();
        showToast('已创建新会话', 'success');
      }
    } catch {
      showToast('创建会话失败', 'error');
    }
  }, [apiFetch, isLoggedIn, loadSessions, persistSessionId, showToast]);

  const handleSelectDepartment = useCallback((departmentCode) => {
    setSelectedDepartment(departmentCode);
    const selected = DEPARTMENT_OPTIONS.find(item => item.code === departmentCode);
    showToast(`已锁定科室：${selected?.zh || departmentCode}`, 'info');
  }, [showToast]);

  const handleClearDepartment = useCallback(() => {
    setSelectedDepartment(null);
    showToast('已切换为自动路由模式', 'info');
  }, [showToast]);

  // ── Clear chat ─────────────────────────────────────────────
  const clearChat = useCallback(async () => {
    if (!isLoggedIn) return;
    if (!window.confirm('确认清空当前会话内容？')) return;
    try {
      const res = await apiFetch('/clear', { method: 'POST' });
      if (res.ok) {
        setMessages([]);
        setChatHistory([]);
        setShowWelcome(true);
        showToast('会话已清空', 'success');
      }
    } catch {
      showToast('清空会话失败', 'error');
    }
  }, [apiFetch, isLoggedIn, showToast]);

  // ── Download chat ──────────────────────────────────────────
  const downloadChat = useCallback(() => {
    if (chatHistory.length === 0) { showToast('暂无可导出的对话', 'error'); return; }
    const content = buildDownloadText(chatHistory);
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `医枢智疗-对话记录-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('对话导出成功', 'success');
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
    const effectiveSession = sessionIdForTask || currentSessionId || sessionHeaderId;
    ecgPollingSessionRef.current = effectiveSession;

    const params = new URLSearchParams({
      tenant_id: identity.tenantId,
      user_id: identity.userId,
      session_id: effectiveSession || '',
    });
    const streamUrl = `${API_BASE}/ecg/monitor/${taskId}/events?${params.toString()}`;
    const es = new EventSource(streamUrl, { withCredentials: true });
    ecgEventSourceRef.current = es;

    es.onmessage = (event) => {
      if (!event?.data) return;
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

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
    };

    es.onerror = () => {
      // If stream breaks before completion, close stream and fallback to current status API once.
      if (!ecgPollingSessionRef.current) return;
      es.close();
      ecgEventSourceRef.current = null;
      (async () => {
        try {
          const res = await apiFetch(
            `/ecg/monitor/${taskId}`,
            {},
            { sessionId: ecgPollingSessionRef.current },
          );
          const data = await res.json();
          if (res.ok && data.status === 'completed' && data.report) {
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
              timestamp: data.report.created_at || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              source: 'ECG Report Skill',
            };
            setMessages(prev => [...prev, botMsg]);
            setChatHistory(prev => [...prev, botMsg]);
            showToast('ECG 报告生成成功', 'success');
            loadSessions();
          } else if (res.ok && data.status === 'failed') {
            const errMsg = {
              type: 'assistant',
              content: data.message || 'ECG 报告制作失败，请稍后重试。',
              timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              source: null,
            };
            setMessages(prev => [...prev, errMsg]);
            setChatHistory(prev => [...prev, errMsg]);
            showToast('ECG 报告制作失败', 'error');
          }
        } catch {
          showToast('ECG 状态流中断，请稍后重试', 'error');
        } finally {
          setIsEcgMonitoring(false);
          ecgPollingSessionRef.current = null;
        }
      })();
    };
  }, [apiFetch, currentSessionId, identity.tenantId, identity.userId, loadSessions, sessionHeaderId, showToast, stopEcgPolling]);

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
      '请确认已完成 ECG 相关数据准备。\n点击“确定”后将按后端当前配置的数据模式生成 PDF 报告。',
    );
    if (!uploadConfirmed) {
      showToast('已取消 ECG 报告制作', 'info');
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
          content: '已确认，正在按后端配置的数据模式生成 PDF 版专家报告。',
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

    const streamMsgId = `assistant-stream-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    setMessages(prev => [
      ...prev,
      { id: streamMsgId, type: 'assistant', content: '', timestamp: time, source: null },
    ]);

    let streamedText = '';
    let finalized = false;

    const updateStreamBubble = (patch) => {
      setMessages(prev => prev.map(msg => (
        msg.id === streamMsgId
          ? { ...msg, ...patch }
          : msg
      )));
    };

    const finalizeStreamBubble = (payload = {}) => {
      if (finalized) return;
      finalized = true;
      const finalText = payload.response || streamedText || '未返回内容';
      const finalSource = payload.source || null;
      const finalTimestamp = payload.timestamp || time;
      updateStreamBubble({
        content: finalText,
        source: finalSource,
        timestamp: finalTimestamp,
      });
      setChatHistory(prev => [
        ...prev,
        {
          type: 'assistant',
          content: finalText,
          timestamp: finalTimestamp,
          source: finalSource,
        },
      ]);
    };

    const handleSseFrame = (frame) => {
      const lines = frame.split('\n');
      let eventName = 'message';
      const dataLines = [];
      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      if (!dataLines.length) return null;
      let payload = {};
      try {
        payload = JSON.parse(dataLines.join('\n'));
      } catch {
        payload = {};
      }
      return { eventName, payload };
    };

    try {
      const chatSessionId = currentSessionId || sessionHeaderId || createClientSessionId();
      persistSessionId(chatSessionId);
      const res = await apiFetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          selected_department: selectedDepartment || null,
        }),
      }, { sessionId: chatSessionId });

      if (!res.ok || !res.body) {
        throw new Error('stream_unavailable');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let donePayload = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const frames = buffer.split('\n\n');
        buffer = frames.pop() || '';
        for (const frame of frames) {
          const parsed = handleSseFrame(frame);
          if (!parsed) continue;
          const { eventName, payload } = parsed;
          if (eventName === 'delta') {
            const delta = payload.delta || '';
            if (!delta) continue;
            streamedText += delta;
            updateStreamBubble({ content: streamedText });
          } else if (eventName === 'done') {
            donePayload = payload;
          } else if (eventName === 'error') {
            throw new Error(payload.message || 'stream_error');
          }
        }
      }

      if (buffer.trim()) {
        const parsed = handleSseFrame(buffer);
        if (parsed?.eventName === 'delta') {
          const delta = parsed.payload?.delta || '';
          streamedText += delta;
        } else if (parsed?.eventName === 'done') {
          donePayload = parsed.payload;
        }
      }

      finalizeStreamBubble(donePayload || {
        response: streamedText,
        source: null,
        timestamp: time,
      });
      showToast('回答已生成', 'success');
      await loadSessions();
    } catch {
      finalizeStreamBubble({
        response: streamedText || '连接异常，请检查网络后重试。',
        source: null,
        timestamp: time,
      });
      showToast('连接异常', 'error');
    } finally {
      setIsTyping(false);
    }
  }, [apiFetch, currentSessionId, inputValue, isLoggedIn, isTyping, loadSessions, persistSessionId, selectedDepartment, sessionHeaderId, showToast]);

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
              <h2 className="gradient-text">医枢智疗·临床协同中枢</h2>
              <div className="status-indicator">
                <div className="status-ring">
                  <span className="ring-pulse" />
                </div>
                <span>
                  {isLoggedIn
                    ? `在线 · ${identity.userId}${selectedDepartment ? ` · ${DEPARTMENT_OPTIONS.find(item => item.code === selectedDepartment)?.zh || selectedDepartment}` : ' · 自动路由'}`
                    : '请先登录'}
                </span>
              </div>
            </div>
            <div className="header-actions">
              <button className="action-btn" title="清空会话" onClick={clearChat}>
                <i className="fas fa-trash" />
              </button>
              <button className="action-btn" title="导出对话" onClick={downloadChat}>
                <i className="fas fa-download" />
              </button>
              <button className="action-btn" title="退出登录" onClick={logout}>
                <i className="fas fa-sign-out-alt" />
              </button>
            </div>
          </header>

          {/* Chat Area */}
          <ChatArea
            messages={messages}
            isTyping={isTyping}
            showWelcome={showWelcome}
            onSelectDepartment={handleSelectDepartment}
            onClearDepartment={handleClearDepartment}
            selectedDepartment={selectedDepartment}
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
