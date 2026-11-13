const STORAGE_KEY = 'linkload.apiBase';

const LOCAL_HOST =
  /^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/i;

export function normalizeApiBase(value) {
  const text = String(value || '').trim();
  if (!text) return '';

  let candidate = text;

  if (!/^https?:\/\//i.test(candidate)) {
    const host = candidate.split('/')[0];
    candidate = `${LOCAL_HOST.test(host) ? 'http' : 'https'}://${candidate}`;
  }

  try {
    const parsed = new URL(candidate);
    if (!['http:', 'https:'].includes(parsed.protocol)) return '';
    return `${parsed.origin}${parsed.pathname.replace(/\/+$/, '')}`;
  } catch {
    return '';
  }
}

const BUILD_API_BASE = normalizeApiBase(
  import.meta.env?.VITE_API_BASE || ''
);

export function getApiBase() {
  let stored = '';

  try {
    stored = localStorage.getItem(STORAGE_KEY) || '';
  } catch {
    // Fall back to build-time configuration.
  }

  return normalizeApiBase(stored) || BUILD_API_BASE;
}

export function setApiBase(value) {
  const base = normalizeApiBase(value);

  try {
    if (base) localStorage.setItem(STORAGE_KEY, base);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage may be unavailable.
  }

  return base;
}

export function isServerConfigured() {
  return true;
}

export function needsServerProbe() {
  return !getApiBase();
}

function isSecurePage() {
  return typeof location !== 'undefined' && location.protocol === 'https:';
}

export function mixedContentRisk(base) {
  if (!isSecurePage()) return false;

  const value = String(base || '').trim();
  if (!/^http:\/\//i.test(value)) return false;

  const host = value.replace(/^http:\/\//i, '').split(/[/:]/)[0];

  return !/^(localhost|127\.0\.0\.1|\[::1\])$/i.test(host);
}