/**
 * QuickAddPanel — slide-in panel to add a job by paste, URL, or PDF.
 *
 * Three tabs: Paste / URL / PDF. On submit, we show the AI loading-steps
 * UI while scoring runs server-side (~5-10s typical), then navigate to
 * the new job's detail page on success.
 */
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Upload } from 'lucide-react';
import { SlidePanel } from './ui/SlidePanel';
import { AILoadingSteps } from './ui/AILoadingSteps';
import { useCreateJob, useCreateJobFromPdf } from '@/api/hooks';
import { ApiError } from '@/api/client';

const STEPS = [
  'Reading the job description…',
  'Matching skills…',
  'Weighing salary and location…',
  'Writing your summary…',
];

type Mode = 'paste' | 'url' | 'pdf';

export function QuickAddPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const [mode, setMode] = useState<Mode>('paste');
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const create = useCreateJob();
  const createFromPdf = useCreateJobFromPdf();

  const busy = create.isPending || createFromPdf.isPending;

  function close() {
    if (!busy) {
      onClose();
      // Don't clear text immediately — slight delay lets the panel
      // finish animating out before wiping so re-opens feel fresh.
      setTimeout(() => {
        setText('');
        setUrl('');
        setFile(null);
        setErr(null);
      }, 200);
    }
  }

  async function submit() {
    setErr(null);
    try {
      let job;
      if (mode === 'pdf') {
        if (!file) return;
        job = await createFromPdf.mutateAsync(file);
      } else {
        job = await create.mutateAsync(
          mode === 'paste'
            ? { source_type: 'paste', description: text }
            : { source_type: 'url', url },
        );
      }
      nav(`/jobs/${job.id}`);
      onClose();
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : 'Something went wrong');
    }
  }

  function pickPdf(f: File | null) {
    if (!f) {
      setFile(null);
      return;
    }
    // Guard here as well as on the server — cheaper UX to fail before upload.
    if (f.type && f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) {
      setErr('Please choose a PDF file.');
      return;
    }
    if (f.size > 5 * 1024 * 1024) {
      setErr('File is larger than 5MB.');
      return;
    }
    setErr(null);
    setFile(f);
  }

  const canSubmit =
    mode === 'paste'
      ? text.length >= 100
      : mode === 'url'
        ? !!url
        : !!file;

  return (
    <SlidePanel open={open} onClose={close} title="Add a job">
      {busy ? (
        <div className="mb-card">
          <div className="mb-display text-lg mb-3">Scoring this match</div>
          <AILoadingSteps steps={STEPS} />
        </div>
      ) : (
        <>
          <div className="flex gap-2 mb-4">
            <TabBtn active={mode === 'paste'} onClick={() => setMode('paste')}>Paste text</TabBtn>
            <TabBtn active={mode === 'url'} onClick={() => setMode('url')}>From URL</TabBtn>
            <TabBtn active={mode === 'pdf'} onClick={() => setMode('pdf')}>Upload PDF</TabBtn>
          </div>

          {mode === 'paste' && (
            <textarea
              value={text} onChange={(e) => setText(e.target.value)}
              className="mb-input min-h-[240px] font-mono text-sm"
              placeholder="Paste the full job description here. Minimum 100 characters."
            />
          )}

          {mode === 'url' && (
            <input
              value={url} onChange={(e) => setUrl(e.target.value)}
              className="mb-input" type="url"
              placeholder="https://boards.greenhouse.io/…"
            />
          )}

          {mode === 'pdf' && (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => pickPdf(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="w-full flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border bg-cream/40 hover:bg-cream/70 text-ink-2 py-10 transition"
              >
                {file ? (
                  <>
                    <FileText size={28} className="text-teal" />
                    <span className="font-medium text-ink">{file.name}</span>
                    <span className="text-xs text-ink-3">
                      {(file.size / 1024).toFixed(0)} KB — click to choose a
                      different file
                    </span>
                  </>
                ) : (
                  <>
                    <Upload size={24} />
                    <span className="font-medium text-ink">Choose a PDF</span>
                    <span className="text-xs text-ink-3">
                      Up to 5MB. Text is extracted locally before scoring.
                    </span>
                  </>
                )}
              </button>
            </div>
          )}

          {err && <div className="mt-3 text-sm text-rust bg-rust-light rounded-lg px-3 py-2">{err}</div>}

          <div className="flex justify-end gap-2 mt-4">
            <button className="mb-btn-ghost" onClick={close}>Cancel</button>
            <button
              className="mb-btn-primary"
              onClick={submit}
              disabled={!canSubmit}
            >
              Score this job
            </button>
          </div>
          {mode === 'paste' && text.length > 0 && text.length < 100 && (
            <p className="mt-2 text-xs text-ink-3">
              {100 - text.length} more characters to go.
            </p>
          )}
        </>
      )}
    </SlidePanel>
  );
}

function TabBtn({ active, children, onClick }: { active: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm transition ${
        active ? 'bg-ink text-white' : 'bg-parchment text-ink-2 hover:text-ink'
      }`}
    >
      {children}
    </button>
  );
}
