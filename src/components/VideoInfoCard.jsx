function formatDuration(seconds) {
  if (!seconds) return null;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}

export default function VideoInfoCard({ video, onChooseQuality }) {
  return (
    <section className="card shadow-sm mt-3" aria-label="Video information">
      <div className="row g-0">
        <div className="col-12 col-sm-5">
          {video.thumbnail ? (
            <img
              src={video.thumbnail}
              alt={`Thumbnail for ${video.title}`}
              className="img-fluid rounded-start h-100 object-fit-cover"
              style={{ minHeight: 160 }}
            />
          ) : (
            <div
              className="bg-secondary-subtle h-100 d-flex align-items-center justify-content-center text-muted p-4"
              aria-hidden="true"
            >
              No preview
            </div>
          )}
        </div>
        <div className="col-12 col-sm-7">
          <div className="card-body d-flex flex-column h-100">
            <div className="d-flex flex-wrap gap-2 mb-2">
              <span className="badge text-bg-primary">{video.platform_label}</span>
              {video.is_live && <span className="badge text-bg-danger">Live</span>}
            </div>
            <h2 className="h5 card-title mb-1">{video.title}</h2>
            {video.uploader && (
              <p className="text-muted small mb-2">{video.uploader}</p>
            )}
            <dl className="row small mb-3">
              <dt className="col-5 col-sm-4">Duration</dt>
              <dd className="col-7 col-sm-8 mb-0">
                {formatDuration(video.duration_seconds) || 'Unknown'}
              </dd>
            </dl>
            <div className="mt-auto d-grid">
              <button
                type="button"
                className="btn btn-primary"
                onClick={onChooseQuality}
              >
                Choose quality
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
