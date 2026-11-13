import { useState } from 'react';
import { ApiError, pingServer } from '../api';
import { getApiBase, mixedContentRisk, normalizeApiBase, setApiBase } from '../config';

export default function ServerSettings({ onSaved, onClose }) {
  const [value, setValue] = useState(getApiBase());
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  async function save(base, check = true) {
    setError('');
    setNotice('');

    if (!base) {
      setError('Enter the full address of your LinkLoad server.');
      return;
    }

    if (check) {
      setBusy(true);
      try {
        await pingServer(base);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? err.message
            : 'Could not reach that server. Please try again.'
        );
        setBusy(false);
        return;
      }
      setBusy(false);
    }

    setApiBase(base);
    setValue(base);
    setNotice('Saved. LinkLoad will use this server.');
    onSaved?.(base);
  }

  function handleSubmit(event) {
    event.preventDefault();
    save(normalizeApiBase(value));
  }

  const stored = getApiBase();

  return (
    <section className="card shadow-sm mt-3" aria-label="Server settings">
      <form className="card-body" onSubmit={handleSubmit} noValidate>
        <div className="d-flex align-items-start justify-content-between gap-2 mb-2">
          <h2 className="h6 mb-0">Server</h2>
          {stored && (
            <button
              type="button"
              className="btn btn-link btn-sm p-0"
              onClick={onClose}
              disabled={busy}
            >
              Close
            </button>
          )}
        </div>

        <p className="text-muted small mb-3">
          LinkLoad reads videos with a Python backend. Enter the address of your
          running LinkLoad server.
        </p>

        <label htmlFor="server-url" className="form-label fw-semibold small">
          Server address
        </label>
        <input
          id="server-url"
          className={`form-control ${error ? 'is-invalid' : ''}`}
          type="text"
          inputMode="url"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="https://linkload.example.com"
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            setError('');
            setNotice('');
          }}
          disabled={busy}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? 'server-error' : 'server-help'}
        />
        {error && (
          <div id="server-error" className="invalid-feedback d-block" role="alert">
            {error}
          </div>
        )}
        {notice && (
          <div className="text-success small mt-2" role="status">
            {notice}
          </div>
        )}
        <p id="server-help" className="form-text">
          Include http:// or https:// for local servers, e.g.{' '}
          <code>http://192.168.1.20:5000</code>.
        </p>

        {mixedContentRisk(normalizeApiBase(value)) && (
          <div className="alert alert-warning py-2 px-3 small" role="status">
            This site is served over HTTPS, so the browser will block an http://
            server. Use the https:// address of your backend.
          </div>
        )}

        <div className="d-flex flex-wrap gap-2">
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? (
              <>
                <span
                  className="spinner-border spinner-border-sm me-2"
                  aria-hidden="true"
                ></span>
                Checking…
              </>
            ) : (
              'Save server'
            )}
          </button>
          {value.trim() && (
            <button
              type="button"
              className="btn btn-outline-secondary"
              onClick={() => save(normalizeApiBase(value), false)}
              disabled={busy}
            >
              Save without testing
            </button>
          )}
        </div>
      </form>
    </section>
  );
}
