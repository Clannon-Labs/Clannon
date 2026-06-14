/**
 * Input-file limits + validation, shared by every composer. These MIRROR the
 * backend for fast client-side feedback only — the backend stays the authority
 * and its 422 (which file, why) is surfaced verbatim. Audio and video are live
 * upload types; `.svg` is intentionally excluded (a vector/XSS-shaped format).
 */
export const MAX_FILES = 10;
export const MAX_FILE_BYTES = 50 * 1024 * 1024;
export const ACCEPTED_INPUT =
  ".txt,.md,.markdown,.csv,.tsv,.json,.jsonl,.yaml,.yml,.xml,.html,.htm,.log,.rtf,.pdf,.png,.jpg,.jpeg,.gif,.webp,.bmp,.tif,.tiff,.mp3,.wav,.m4a,.aac,.ogg,.flac,.mp4,.mov,.webm,.avi";

const TEXT_LIKE = /\.(txt|md|markdown|csv|tsv|json|jsonl|ya?ml|xml|html?|log|rtf)$/i;
const IMAGE_LIKE = /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i;
const AUDIO_LIKE = /\.(mp3|wav|m4a|aac|ogg|flac)$/i;
const VIDEO_LIKE = /\.(mp4|mov|webm|avi)$/i;

/** A reason to reject a file before upload, or null if it's acceptable today. */
export function rejectInputFile(file: File): string | null {
  if (file.size > MAX_FILE_BYTES) return `${file.name} is larger than 50 MB.`;
  const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
  const isText = file.type.startsWith("text/") || TEXT_LIKE.test(file.name);
  const isImage =
    (file.type.startsWith("image/") && file.type !== "image/svg+xml") ||
    IMAGE_LIKE.test(file.name);
  const isAudio = file.type.startsWith("audio/") || AUDIO_LIKE.test(file.name);
  const isVideo = file.type.startsWith("video/") || VIDEO_LIKE.test(file.name);
  if (!isPdf && !isText && !isImage && !isAudio && !isVideo) {
    return `${file.name}: only text files, PDFs, images, audio, and video are supported.`;
  }
  return null;
}

/** Audio/video, which can be heavy enough to exceed the model's inline limit. */
export function isAudioOrVideo(file: File): boolean {
  return (
    file.type.startsWith("audio/") ||
    file.type.startsWith("video/") ||
    AUDIO_LIKE.test(file.name) ||
    VIDEO_LIKE.test(file.name)
  );
}
