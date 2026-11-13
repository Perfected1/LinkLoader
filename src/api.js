import { getApiBase, mixedContentRisk } from './config';

export class ApiError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
  }
}

const MIXED_CONTENT_MESSAGE =
  'This page is served over HTTPS, so the browser blocks an http:// server. ' +
  'Use the https:// address of your LinkLoad backend.';

function apiUrl(path, base = getApiBase()) {
  return `${base}${path}`;
}

async function request(path, options = {}) {
  const url = apiUrl(path);

  let response;
  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
  } catch {
    if (mixedContentRisk(url)) {
      throw new ApiError(MIXED_CONTENT_MESSAGE, 'mixed_content');
    }
    throw new ApiError(
      'Could not reach the server. Check your connection and the server address in settings.',
      'network_error'
    );
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON response; fall through to a generic error below.
  }

  if (!response.ok || !body || body.ok === false) {
    const message =
      body && body.error && body.error.message
        ? body.error.message
        : 'Something went wrong. Please try again.';
    const code = body && body.error ? body.error.code : 'server_error';
    throw new ApiError(message, code);
  }

  return body.data;
}

/** Check that a LinkLoad backend answers at the given origin. */
export async function pingServer(base) {
  let url;
  try {
    url = apiUrl('/api/health', base ?? getApiBase());
  } catch (err) {
    throw new ApiError('Enter a server address first.', 'no_server');
  }

  try {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const body = await response.json();
    if (!response.ok || !body || body.status !== 'ok') throw new Error('bad response');
    return true;
  } catch {
    if (mixedContentRisk(url)) {
      throw new ApiError(MIXED_CONTENT_MESSAGE, 'mixed_content');
    }
    throw new ApiError(
      'No LinkLoad server answered there. Check the address and that the backend is running.',
      'network_error'
    );
  }
}

export function validateLink(url) {
  return request('/api/validate', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function fetchVideoInfo(url) {
  return request('/api/info', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function fetchFormats(url) {
  return request('/api/formats', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function suggestAiClips(url, prompt = '', duration = null) {
  return request('/api/ai/clips', {
    method: 'POST',
    body: JSON.stringify({ url, prompt, duration }),
  });
}

function filenameFromDisposition(header) {
  if (!header) return null;
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      return utf8[1].trim();
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : null;
}

export async function downloadVideo(url, height, clip = null) {
  const target = apiUrl('/api/download');

  let response;
  try {
    response = await fetch(target, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url,
        height,
        ...(clip ? { start: clip.start, end: clip.end } : {}),
      }),
    });
  } catch {
    if (mixedContentRisk(target)) {
      throw new ApiError(MIXED_CONTENT_MESSAGE, 'mixed_content');
    }
    throw new ApiError(
      'Could not reach the server. Check your connection and the server address in settings.',
      'network_error'
    );
  }

  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error response.
    }
    throw new ApiError(
      body && body.error && body.error.message
        ? body.error.message
        : 'The download could not be completed. Please try again.',
      body && body.error ? body.error.code : 'download_failed'
    );
  }

  const blob = await response.blob();
  return {
    blob,
    filename:
      filenameFromDisposition(response.headers.get('Content-Disposition')) ||
      'linkload-video.mp4',
  };
}
