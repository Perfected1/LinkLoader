import { useEffect, useState } from 'react';
import './App.css';
import { ApiError, fetchVideoInfo, pingServer, validateLink } from './api';
import {
  getApiBase,
  isServerConfigured,
  needsServerProbe,
} from './config';
import ServerSettings from './components/ServerSettings';
import VideoInfoCard from './components/VideoInfoCard';
import QualitySelector from './components/QualitySelector';

function LoadingCard() {
  return (
    <div className="card shadow-sm mt-3 p-4" aria-live="polite">
      <div className="d-flex align-items-center gap-3">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">Loading</span>
        </div>
        <div>
          <p className="mb-0 fw-semibold">Reading video details…</p>
          <p className="mb-0 small text-muted">This can take a few seconds.</p>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [link, setLink] = useState('');
  const [error, setError] = useState('');
  const [video, setVideo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showQuality, setShowQuality] = useState(false);
  const [configured, setConfigured] = useState(isServerConfigured());
  const [probing, setProbing] = useState(needsServerProbe());
  const [showSettings, setShowSettings] = useState(
    !isServerConfigured() && !needsServerProbe()
  );

  // On a static host (Vercel) nothing answers /api, so check before offering
  // the form and fall back to asking for the backend address.
  useEffect(() => {
    if (!needsServerProbe()) return undefined;
    let cancelled = false;
    pingServer(getApiBase())
      .catch(() => {
        if (cancelled) return;
        setConfigured(false);
        setShowSettings(true);
      })
      .finally(() => {
        if (!cancelled) setProbing(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    setError('');
    setVideo(null);
    setShowQuality(false);

    if (!isServerConfigured()) {
      setShowSettings(true);
      setError('Add your LinkLoad server address first.');
      return;
    }

    if (!link.trim()) {
      setError('Please paste a video link first.');
      return;
    }

    setLoading(true);
    try {
      await validateLink(link);
      const info = await fetchVideoInfo(link);
      setVideo(info);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'no_server') setShowSettings(true);
      setError(
        err instanceof ApiError ? err.message : 'Something went wrong. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  }

  function handleLinkChange(value) {
    setLink(value);
    if (error) setError('');
    if (video) setVideo(null);
    setShowQuality(false);
  }

  function handleServerSaved() {
    setConfigured(true);
    setShowSettings(false);
    setError('');
  }

  return (
    <div className="app-shell d-flex align-items-center justify-content-center min-vh-100 py-4">
      <div className="w-100 px-3" style={{ maxWidth: 620 }}>
        <header className="mb-4">
          <div className="d-flex justify-content-end mb-1">
            <button
              type="button"
              className="btn btn-link btn-sm text-muted p-0 text-decoration-none"
              onClick={() => setShowSettings((open) => !open)}
              aria-expanded={showSettings}
            >
              {configured ? `Server: ${getApiBase() || 'this site'}` : 'Set up server'}
            </button>
          </div>
          <h1 className="display-5 fw-bold text-center mb-1">
            <i className="bi bi-cloud-arrow-down-fill text-primary me-2" aria-hidden="true"></i>
            LinkLoad
          </h1>
          <p className="lead text-muted text-center mb-0">
            Download online videos in one click
          </p>
        </header>

        <main>
          {probing && (
            <p className="text-muted small text-center mt-3" role="status">
              <span
                className="spinner-border spinner-border-sm me-2"
                aria-hidden="true"
              ></span>
              Connecting…
            </p>
          )}

          {!probing && showSettings && (
            <ServerSettings
              onSaved={handleServerSaved}
              onClose={() => setShowSettings(false)}
            />
          )}

          {!probing && configured && (
            <form
              className="card p-4 shadow-sm mt-3"
              onSubmit={handleSubmit}
              noValidate
              aria-label="Video link form"
            >
              <label htmlFor="video-link" className="form-label fw-semibold">
                Video link
              </label>
              <input
                id="video-link"
                type="url"
                inputMode="url"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                className={`form-control form-control-lg ${error ? 'is-invalid' : ''}`}
                placeholder="Paste a link — YouTube, Facebook, X, Instagram, TikTok…"
                value={link}
                onChange={(e) => handleLinkChange(e.target.value)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? 'link-error' : undefined}
                disabled={loading}
              />
              {error && (
                <div id="link-error" className="invalid-feedback d-block" role="alert">
                  {error}
                </div>
              )}
              {!error && (
                <p className="form-text mb-0">
                  Works with YouTube, Facebook, X, Instagram, TikTok, Twitch, Reddit,
                  Vimeo and Dailymotion.
                </p>
              )}

              <button
                className="btn btn-primary btn-lg w-100 mt-3"
                type="submit"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span
                      className="spinner-border spinner-border-sm me-2"
                      aria-hidden="true"
                    ></span>
                    Analyzing…
                  </>
                ) : (
                  'Analyze Link'
                )}
              </button>
            </form>
          )}

          {loading && <LoadingCard />}

          {video && !loading && (
            <VideoInfoCard
              video={video}
              onChooseQuality={() => setShowQuality(true)}
            />
          )}

          {showQuality && video && (
            <QualitySelector
              url={video.webpage_url || link}
              duration={video.duration_seconds}
              onBack={() => setShowQuality(false)}
            />
          )}

          {!probing && !configured && !showSettings && (
            <button
              type="button"
              className="btn btn-primary w-100 mt-3"
              onClick={() => setShowSettings(true)}
            >
              Set up server
            </button>
          )}
        </main>

        <footer className="text-center text-muted mt-4 small">
          LinkLoader 2026
        </footer>
      </div>
    </div>
  );
}

export default App;
