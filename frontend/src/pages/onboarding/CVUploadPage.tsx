/**
 * CVUploadPage — step 1 of onboarding.
 *
 * Accepts a single PDF/DOCX/TXT up to 5 MB and POSTs it to
 * /profile/upload-cv. The backend extracts + Claude-parses the text
 * and stashes a ParsedCV on the profile row; we then move the user
 * to the clarifying-questions step.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, FileText } from 'lucide-react';
import { uploadFile } from '@/api/upload';
import { ApiError } from '@/api/client';
import { AILoadingSteps } from '@/components/ui/AILoadingSteps';

const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];

const STEPS = [
  'Reading your CV…',
  'Pulling out skills and roles…',
  'Summarising your experience…',
];

export function CVUploadPage() {
  const nav = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Drag highlight — purely visual. We track a boolean rather than
  // CSS-only :hover so the drop zone stays highlighted while the user
  // is actually dragging (not just hovering).
  const [dragOver, setDragOver] = useState(false);

  function pick(f: File | null) {
    setErr(null);
    if (!f) return;
    if (f.size > MAX_BYTES) return setErr('File is over 5 MB.');
    // Some browsers / OSes report Word docs without a recognised MIME
    // type when dropped. Fall back to the extension if the MIME check
    // doesn't match — the backend re-validates via python-magic on
    // signature bytes, so a permissive client check is safe here.
    const allowedExt = /\.(pdf|docx|doc|txt)$/i.test(f.name);
    if (!ALLOWED.includes(f.type) && !allowedExt) {
      return setErr('PDF or Word documents only.');
    }
    setFile(f);
  }

  async function submit() {
    if (!file) return;
    setErr(null);
    setBusy(true);
    try {
      await uploadFile('/profile/upload-cv', file);
      nav('/onboarding/questions');
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : 'Upload failed');
      setBusy(false);
    }
  }

  return (
    <div className="min-h-full bg-cream flex items-center justify-center p-6">
      <div className="mb-card w-full max-w-xl">
        <div className="mb-display text-2xl mb-1">Let's start with your CV</div>
        <p className="text-sm text-ink-2 mb-5">
          We'll read it and ask a few quick questions to fill in the gaps.
        </p>

        {busy ? (
          <AILoadingSteps steps={STEPS} />
        ) : (
          <>
            <label
              className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl p-8 cursor-pointer transition ${
                dragOver
                  ? 'border-teal bg-parchment'
                  : 'border-border hover:bg-parchment/50'
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                // dataTransfer.files is a FileList; we only care about
                // the first. Extra drops are ignored rather than
                // queued — CV upload is explicitly single-file.
                pick(e.dataTransfer.files[0] ?? null);
              }}
            >
              <UploadCloud size={28} className="text-ink-3" />
              <span className="text-sm text-ink-2">
                {file ? (
                  <span className="flex items-center gap-2 text-ink">
                    <FileText size={14} />
                    {file.name}
                  </span>
                ) : (
                  <>
                    <span className="font-medium text-ink">
                      Drag and drop your CV
                    </span>{' '}
                    or click to choose a file
                  </>
                )}
              </span>
              <span className="text-xs text-ink-3">
                PDF or Word documents only · max 5 MB
              </span>
              <input
                type="file"
                accept=".pdf,.docx,.doc"
                className="hidden"
                onChange={(e) => pick(e.target.files?.[0] ?? null)}
              />
            </label>

            {err && <div className="mt-3 text-sm text-rust bg-rust-light rounded-lg px-3 py-2">{err}</div>}

            <div className="flex justify-end mt-5">
              <button className="mb-btn-primary" onClick={submit} disabled={!file}>
                Upload and continue
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
