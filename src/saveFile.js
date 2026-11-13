
function safeFilename(filename) {
  const cleaned = String(filename || '')
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .trim();

  return cleaned || 'linkload-video.mp4';
}

export async function saveDownload(blob, filename) {
  const name = safeFilename(filename);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');

  anchor.href = objectUrl;
  anchor.download = name;

  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

  return {
    message: 'Download started. Check your browser downloads.',
  };
}
