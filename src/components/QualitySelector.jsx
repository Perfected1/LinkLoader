import { useEffect, useRef, useState } from 'react';
import { ApiError, downloadVideo, fetchFormats, suggestAiClips } from '../api';
import { saveDownload } from '../saveFile';

function formatSize(bytes) {
  if (!bytes || bytes <= 0) return null;
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatClock(seconds) {
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}

// Accepts plain seconds ("90", "90.5") or clock values ("1:30", "1:02:30").
// Returns null for empty input and NaN for anything unparsable.
function parseTimeInput(value) {
  const text = value.trim();
  if (!text) return null;
  if (/^\d+(\.\d+)?$/.test(text)) return Number(text);
  if (/^\d{1,3}(:\d{1,2}){1,2}(\.\d+)?$/.test(text)) {
    return text.split(':').reduce((total, part) => total * 60 + Number(part), 0);
  }
  return NaN;
}

export default function QualitySelector({ url, duration, onBack }) {
  const [formats, setFormats] = useState([]);
  const [selected, setSelected] = useState('best');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [notice, setNotice] = useState('');
  const [clipStart, setClipStart] = useState('');
  const [clipEnd, setClipEnd] = useState('');
  const [clipError, setClipError] = useState('');
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiClips, setAiClips] = useState([]);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');
  const [aiNotice, setAiNotice] = useState('');
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const data = await fetchFormats(url);
        if (cancelled.current) return;
        setFormats(data.options || []);
      } catch (err) {
        if (cancelled.current) return;
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not load available qualities. Please try again.'
        );
      } finally {
        if (!cancelled.current) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled.current = true;
    };
  }, [url]);

  function readClip() {
    const startValue = parseTimeInput(clipStart);
    const endValue = parseTimeInput(clipEnd);

    if (Number.isNaN(startValue) || Number.isNaN(endValue)) {
      setClipError('Enter clip times as seconds or mm:ss.');
      return undefined;
    }
    if (startValue === null && endValue === null) return null;

    const start = startValue ?? 0;
    const end = endValue ?? (duration || null);
    if (end === null) {
      setClipError('Enter an end time for the clip.');
      return undefined;
    }
    if (end <= start) {
      setClipError('The end time must be after the start time.');
      return undefined;
    }
    if (duration && end > duration + 0.5) {
      setClipError(`The video ends at ${formatClock(duration)}.`);
      return undefined;
    }
    return { start, end };
  }

  async function runAi(usePrompt) {
    if (usePrompt && !aiPrompt.trim()) {
      setAiError('Describe the moment you want to find first.');
      return;
    }
    setAiError('');
    setAiNotice('');
    setAiLoading(true);
    try {
      const data = await suggestAiClips(
        url,
        usePrompt ? aiPrompt.trim() : '',
        duration
      );
      setAiClips(data.clips || []);
    } catch (err) {
      setAiClips([]);
      setAiError(
        err instanceof ApiError
          ? err.message
          : 'AI clipping failed. Please try again.'
      );
    } finally {
      setAiLoading(false);
    }
  }

  function applyAiClip(clip) {
    const start = formatClock(clip.start);
    const end = formatClock(clip.end);
    setClipStart(start);
    setClipEnd(end);
    setClipError('');
    setAiNotice(`Clip range set to ${start}–${end}. Choose a quality, then download.`);
  }

  async function handleDownload() {
    setError('');
    setNotice('');
    setClipError('');

    const clip = readClip();
    if (clip === undefined) return;

    setDownloading(true);
    try {
      const height = selected === 'best' ? 'best' : Number(selected);
      const { blob, filename } = await downloadVideo(url, height, clip);
      const { message } = await saveDownload(blob, filename);
      setNotice(message);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'The download could not be completed. Please try again.'
      );
    } finally {
      setDownloading(false);
    }
  }

  return (
    <section className="card shadow-sm mt-3" aria-label="Quality selection">
      <div className="card-body">
        <div className="d-flex align-items-start justify-content-between gap-2 mb-3">
          <h2 className="h6 mb-0">Choose a quality</h2>
          <button
            type="button"
            className="btn btn-link btn-sm p-0"
            onClick={onBack}
            disabled={downloading}
          >
            Back
          </button>
        </div>

        {loading && (
          <p className="d-flex align-items-center gap-2 text-muted mb-0" role="status">
            <span className="spinner-border spinner-border-sm" aria-hidden="true"></span>
            Loading available qualities…
          </p>
        )}

        {!loading && error && (
          <div className="alert alert-danger py-2 mb-0" role="alert">
            {error}
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="border rounded p-3 mb-3 bg-body-tertiary">
              <div className="d-flex align-items-center justify-content-between mb-1">
                <p className="fw-semibold small mb-0">AI clips</p>
                <span className="badge text-bg-info">Beta</span>
              </div>
              <p className="text-muted small mb-2">
                Let AI pick a moment from the video&apos;s subtitles, or describe the
                part you want.
              </p>
              <div className="input-group mb-2">
                <label htmlFor="ai-prompt" className="visually-hidden">
                  Describe the moment you want
                </label>
                <input
                  id="ai-prompt"
                  className="form-control"
                  type="text"
                  autoComplete="off"
                  placeholder="Describe a moment, e.g. the product demo"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  disabled={aiLoading || downloading}
                />
                <button
                  type="button"
                  className="btn btn-outline-primary"
                  onClick={() => runAi(true)}
                  disabled={aiLoading || downloading}
                >
                  Find moment
                </button>
              </div>
              <button
                type="button"
                className="btn btn-outline-secondary btn-sm w-100"
                onClick={() => runAi(false)}
                disabled={aiLoading || downloading}
              >
                Suggest highlights
              </button>

              {aiLoading && (
                <p
                  className="d-flex align-items-center gap-2 text-muted small mt-2 mb-0"
                  role="status"
                >
                  <span
                    className="spinner-border spinner-border-sm"
                    aria-hidden="true"
                  ></span>
                  Reading the subtitles…
                </p>
              )}
              {aiError && !aiLoading && (
                <div className="text-danger small mt-2" role="alert">
                  {aiError}
                </div>
              )}
              {aiNotice && !aiLoading && aiClips.length > 0 && (
                <div className="text-success small mt-2" role="status">
                  {aiNotice}
                </div>
              )}

              {aiClips.length > 0 && !aiLoading && (
                <ul className="list-unstyled mt-3 mb-0">
                  {aiClips.map((clip, index) => (
                    <li
                      key={`${clip.start}-${clip.end}-${index}`}
                      className="border-top pt-2 mt-2"
                    >
                      <div className="d-flex justify-content-between gap-2">
                        <span className="fw-semibold small">{clip.title}</span>
                        <span className="text-muted small text-nowrap">
                          {formatClock(clip.start)}–{formatClock(clip.end)}
                        </span>
                      </div>
                      {clip.reason && (
                        <p className="text-muted small mb-1">{clip.reason}</p>
                      )}
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-success"
                        onClick={() => applyAiClip(clip)}
                        disabled={downloading}
                      >
                        Use this clip
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="border rounded p-3 mb-3">
              <p className="fw-semibold small mb-1">
                Clip a section <span className="text-muted fw-normal">(optional)</span>
              </p>
              <p className="text-muted small mb-2">
                Leave both blank to download the whole video
                {duration ? ` (${formatClock(duration)})` : ''}.
              </p>
              <div className="row g-2">
                <div className="col-6">
                  <label htmlFor="clip-start" className="form-label small mb-1">
                    Start
                  </label>
                  <input
                    id="clip-start"
                    className={`form-control ${clipError ? 'is-invalid' : ''}`}
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="0:00"
                    value={clipStart}
                    onChange={(e) => {
                      setClipStart(e.target.value);
                      setClipError('');
                    }}
                    disabled={downloading}
                    aria-describedby="clip-help"
                  />
                </div>
                <div className="col-6">
                  <label htmlFor="clip-end" className="form-label small mb-1">
                    End
                  </label>
                  <input
                    id="clip-end"
                    className={`form-control ${clipError ? 'is-invalid' : ''}`}
                    type="text"
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder={duration ? formatClock(duration) : '1:30'}
                    value={clipEnd}
                    onChange={(e) => {
                      setClipEnd(e.target.value);
                      setClipError('');
                    }}
                    disabled={downloading}
                    aria-describedby="clip-help"
                  />
                </div>
              </div>
              {clipError && (
                <div className="text-danger small mt-2" role="alert">
                  {clipError}
                </div>
              )}
              <p id="clip-help" className="form-text mb-0">
                Use seconds or mm:ss. The clip is saved as its own MP4.
              </p>
            </div>

            <fieldset disabled={downloading}>
              <legend className="visually-hidden">Available video qualities</legend>
              <div className="list-group mb-3">
                <label className="list-group-item d-flex align-items-center gap-2">
                  <input
                    className="form-check-input mt-0"
                    type="radio"
                    name="quality"
                    value="best"
                    checked={selected === 'best'}
                    onChange={() => setSelected('best')}
                  />
                  <span className="fw-semibold flex-grow-1">Best available</span>
                  <span className="badge text-bg-secondary">Auto</span>
                </label>
                {formats.map((option) => (
                  <label
                    key={option.height}
                    className="list-group-item d-flex align-items-center gap-2"
                  >
                    <input
                      className="form-check-input mt-0"
                      type="radio"
                      name="quality"
                      value={option.height}
                      checked={selected === String(option.height)}
                      onChange={() => setSelected(String(option.height))}
                    />
                    <span className="flex-grow-1">
                      {option.label}
                      {option.fps && option.fps > 30 && (
                        <span className="text-muted small ms-1">{option.fps}fps</span>
                      )}
                    </span>
                    {formatSize(option.filesize) && (
                      <span className="text-muted small">
                        ~{formatSize(option.filesize)}
                      </span>
                    )}
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="d-grid">
              <button
                type="button"
                className="btn btn-success"
                onClick={handleDownload}
                disabled={downloading}
              >
                {downloading ? (
                  <>
                    <span
                      className="spinner-border spinner-border-sm me-2"
                      aria-hidden="true"
                    ></span>
                    Preparing download…
                  </>
                ) : (
                  'Download video'
                )}
              </button>
            </div>

            <p className="small text-muted mt-2 mb-0">
              Only download videos you own or have permission to save.
            </p>
          </>
        )}

        {notice && (
          <div className="alert alert-success py-2 mt-3 mb-0" role="status">
            {notice}
          </div>
        )}
      </div>
    </section>
  );
}
