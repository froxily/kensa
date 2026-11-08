import { useId, useState, type SubmitEvent } from "react";
import { useNavigate } from "react-router";

import { Alert } from "../components/ui/Alert";
import { buttonPrimary, buttonSecondary } from "../components/ui/button";
import { useHealth } from "../features/health/useHealth";
import {
  useCreateInvestigation,
  useGitHubLookup,
  useSamples,
} from "../features/investigations/hooks";
import type { CreateInvestigationBody, Provider } from "../features/investigations/types";
import { format, useLocale, useStrings } from "../i18n";
import { IS_REPLAY } from "../lib/api/mode";
import { formatDateTime } from "../lib/format";

const MAX_FILE_BYTES = 2_000_000;
type Method = "paste" | "upload" | "sample" | "github";

const fieldClass =
  "mt-1 w-full rounded-md border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700";

export function NewInvestigationPage() {
  const strings = useStrings();
  const { locale } = useLocale();
  const c = strings.create;
  const ids = {
    error: useId(),
    title: useId(),
    paste: useId(),
    file: useId(),
    sample: useId(),
    githubUrl: useId(),
    githubLog: useId(),
  };
  const navigate = useNavigate();
  const health = useHealth();
  const samples = useSamples();
  const create = useCreateInvestigation();
  const lookup = useGitHubLookup();

  const modelReady = health.data?.ollama.status === "ok";
  const [method, setMethod] = useState<Method>("paste");
  const [chosenProvider, setProvider] = useState<Provider | null>(null);
  const provider: Provider = chosenProvider ?? (modelReady ? "ollama" : "mock");
  const [title, setTitle] = useState("");
  const [logText, setLogText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [sampleId, setSampleId] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [githubLog, setGithubLog] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  async function buildBody(): Promise<CreateInvestigationBody | string> {
    const base = { provider, ...(title.trim() ? { title: title.trim() } : {}) };
    if (method === "paste") {
      return logText.trim() ? { ...base, source: "paste", log_text: logText } : c.errors.emptyLog;
    }
    if (method === "upload") {
      if (!file) return c.errors.noFile;
      if (file.size > MAX_FILE_BYTES) return c.errors.fileTooLarge;
      try {
        return { ...base, source: "upload", log_text: await file.text(), document_name: file.name };
      } catch {
        return c.errors.readFailed;
      }
    }
    if (method === "github") {
      const result = lookup.data;
      if (
        result?.kind !== "run" ||
        !result.run ||
        jobId === null ||
        !result.jobs.some((job) => job.id === jobId)
      )
        return c.github.requiredRun;
      if (!result.token_configured && !githubLog.trim()) return c.github.requiredLog;
      return {
        ...base,
        source: "github",
        github: {
          owner: result.owner,
          repo: result.repo,
          run_id: result.run.id,
          job_id: jobId,
          ...(result.attempt ? { attempt: result.attempt } : {}),
        },
        ...(githubLog.trim() ? { log_text: githubLog } : {}),
      };
    }
    return sampleId ? { ...base, source: "sample", sample_id: sampleId } : c.errors.noSample;
  }

  async function onSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    const body = await buildBody();
    if (typeof body === "string") {
      setFormError(body);
      return;
    }
    create.mutate(body, {
      onSuccess: (created) => {
        void navigate(`/investigations/${created.id}`);
      },
    });
  }

  const error = formError ?? (create.isError ? create.error.message : null);
  const methods: { value: Method; label: string }[] = [
    { value: "paste", label: c.paste },
    { value: "upload", label: c.upload },
    { value: "sample", label: c.sample },
    { value: "github", label: c.github.option },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{c.title}</h1>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{c.intro}</p>
      </div>
      {IS_REPLAY && <Alert tone="info" title={strings.replay.createDisabled} />}

      <form
        onSubmit={(event) => void onSubmit(event)}
        noValidate
        aria-describedby={error ? ids.error : undefined}
        className="space-y-6"
      >
        <fieldset>
          <legend className="text-sm font-semibold">{c.inputLegend}</legend>
          <div className="mt-2 flex flex-wrap gap-4">
            {methods.map((m) => (
              <label key={m.value} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="method"
                  value={m.value}
                  checked={method === m.value}
                  onChange={() => {
                    setMethod(m.value);
                    setFormError(null);
                  }}
                />
                {m.label}
              </label>
            ))}
          </div>
        </fieldset>

        {method === "paste" && (
          <div>
            <label htmlFor={ids.paste} className="text-sm font-medium">
              {c.pasteLabel}
            </label>
            <textarea
              id={ids.paste}
              value={logText}
              onChange={(e) => {
                setLogText(e.target.value);
              }}
              rows={12}
              spellCheck={false}
              placeholder={c.pastePlaceholder}
              className={`${fieldClass} font-mono`}
            />
          </div>
        )}

        {method === "upload" && (
          <div>
            <label htmlFor={ids.file} className="text-sm font-medium">
              {c.fileLabel}
            </label>
            <input
              id={ids.file}
              type="file"
              accept=".log,.txt,text/plain"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
              }}
              className="mt-1 block text-sm"
            />
          </div>
        )}

        {method === "sample" && (
          <div>
            <label htmlFor={ids.sample} className="text-sm font-medium">
              {c.sampleLabel}
            </label>
            <select
              id={ids.sample}
              value={sampleId}
              onChange={(e) => {
                setSampleId(e.target.value);
              }}
              className={fieldClass}
            >
              <option value="">—</option>
              {samples.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title} ({strings.common.synthetic})
                </option>
              ))}
            </select>
            {sampleId && (
              <p className="mt-1 text-xs text-muted">
                {samples.data?.find((s) => s.id === sampleId)?.description}
              </p>
            )}
          </div>
        )}

        {method === "github" && (
          <div className="space-y-4">
            <div>
              <label htmlFor={ids.githubUrl} className="text-sm font-medium">
                {c.github.url}
              </label>
              <input
                id={ids.githubUrl}
                type="url"
                value={githubUrl}
                onChange={(e) => {
                  setGithubUrl(e.target.value);
                  lookup.reset();
                  setJobId(null);
                }}
                className={fieldClass}
              />
              <p className="mt-1 text-xs text-muted">{c.github.hint}</p>
              <button
                type="button"
                className={`${buttonSecondary} mt-2`}
                disabled={IS_REPLAY || lookup.isPending}
                onClick={() => {
                  setJobId(null);
                  lookup.mutate(githubUrl, {
                    onSuccess: (result) => {
                      setJobId(result.selected_job_id);
                    },
                  });
                }}
              >
                {lookup.isPending ? c.github.looking : c.github.lookup}
              </button>
            </div>
            {lookup.isError && <Alert tone="danger" title={lookup.error.message} urgent />}
            {lookup.data?.kind === "repository" && (
              <fieldset>
                <legend className="text-sm font-semibold">{c.github.runs}</legend>
                {lookup.data.runs.length === 0 ? (
                  <p className="mt-2 text-sm text-muted">{c.github.empty}</p>
                ) : (
                  <div className="mt-2 space-y-2">
                    {lookup.data.runs.map((run) => (
                      <label key={run.id} className="flex items-start gap-2 text-sm">
                        <input
                          type="radio"
                          name="githubRun"
                          disabled={lookup.isPending}
                          onChange={() => {
                            setJobId(null);
                            lookup.mutate(run.html_url, {
                              onSuccess: (result) => {
                                setJobId(result.selected_job_id);
                              },
                            });
                          }}
                        />
                        <span>
                          {run.display_title}
                          <span className="block text-xs text-muted">
                            {run.name} #{run.run_number} · {run.head_branch} ·{" "}
                            {run.head_sha.slice(0, 7)} · {formatDateTime(run.created_at, locale)}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </fieldset>
            )}
            {lookup.data?.kind === "run" && lookup.data.run && (
              <>
                <p className="text-sm">
                  {format(c.github.summary, {
                    name: lookup.data.run.name,
                    number: lookup.data.run.run_number,
                    attempt: lookup.data.attempt ?? lookup.data.run.run_attempt,
                    sha: lookup.data.run.head_sha.slice(0, 7),
                  })}
                </p>
                <fieldset>
                  <legend className="text-sm font-semibold">{c.github.jobs}</legend>
                  <div className="mt-2 space-y-2">
                    {lookup.data.jobs.map((job) => (
                      <label key={job.id} className="flex items-start gap-2 text-sm">
                        <input
                          type="radio"
                          name="githubJob"
                          checked={jobId === job.id}
                          onChange={() => {
                            setJobId(job.id);
                          }}
                        />
                        <span>
                          {job.name}
                          {job.failed_steps.map((step) => (
                            <span key={step.number} className="block text-xs text-muted">
                              {format(c.github.failedStep, { name: step.name })}
                            </span>
                          ))}
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                {lookup.data.token_configured ? (
                  <p className="text-sm text-muted">{c.github.downloaded}</p>
                ) : (
                  <div>
                    <label htmlFor={ids.githubLog} className="text-sm font-medium">
                      {c.github.log}
                    </label>
                    <p className="mt-1 text-xs text-muted">
                      {c.github.logHelp}{" "}
                      {lookup.data.jobs.find((job) => job.id === jobId) && (
                        <a
                          href={lookup.data.jobs.find((job) => job.id === jobId)?.html_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sky-700 underline dark:text-sky-400"
                        >
                          {c.github.jobPage}{" "}
                          <span className="sr-only">{strings.common.opensNewTab}</span>
                        </a>
                      )}
                    </p>
                    <textarea
                      id={ids.githubLog}
                      required
                      value={githubLog}
                      onChange={(e) => {
                        setGithubLog(e.target.value);
                      }}
                      rows={12}
                      spellCheck={false}
                      className={`${fieldClass} font-mono`}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        )}

        <div>
          <label htmlFor={ids.title} className="text-sm font-medium">
            {c.titleLabel}
          </label>
          <input
            id={ids.title}
            value={title}
            maxLength={200}
            onChange={(e) => {
              setTitle(e.target.value);
            }}
            className={fieldClass}
          />
          <p className="mt-1 text-xs text-muted">{c.titleHint}</p>
        </div>

        <fieldset>
          <legend className="text-sm font-semibold">{c.providerLegend}</legend>
          <div className="mt-2 space-y-2">
            {(
              [
                ["ollama", c.providerOllama, c.providerOllamaHint],
                ["mock", c.providerMock, c.providerMockHint],
              ] as const
            ).map(([value, name, hint]) => (
              <label key={value} className="flex items-start gap-2 text-sm">
                <input
                  type="radio"
                  name="provider"
                  value={value}
                  checked={provider === value}
                  onChange={() => {
                    setProvider(value);
                  }}
                  className="mt-1"
                />
                <span>
                  <span className="font-medium">{name}</span>
                  <span className="block text-xs text-muted">{hint}</span>
                </span>
              </label>
            ))}
          </div>
          {health.data && !modelReady && (
            <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              {c.modelUnavailable}: {strings.health.status[health.data.ollama.status]}.
            </p>
          )}
        </fieldset>

        {error && (
          <div id={ids.error}>
            <Alert tone="danger" title={error} urgent />
          </div>
        )}

        <button type="submit" className={buttonPrimary} disabled={IS_REPLAY || create.isPending}>
          {create.isPending ? (method === "github" ? c.github.importing : c.submitting) : c.submit}
        </button>
      </form>
    </div>
  );
}
