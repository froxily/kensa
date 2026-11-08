import { format, useStrings } from "../../../i18n";
import type { GitHubRunRecord } from "../types";

export function GitHubRunCard({ run }: { run: GitHubRunRecord }) {
  const strings = useStrings();
  const g = strings.githubRun;
  const repoUrl = `https://github.com/${run.owner}/${run.repo}`;
  const linkClass = "text-sky-700 underline dark:text-sky-400";
  const external = (url: string, text: string) => (
    <a href={url} target="_blank" rel="noopener noreferrer" className={linkClass}>
      {text} <span className="sr-only">{strings.common.opensNewTab}</span>
    </a>
  );
  return (
    <section
      aria-labelledby="github-run-title"
      className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
    >
      <h2 id="github-run-title" className="text-base font-semibold">
        {g.title}
      </h2>
      <div className="space-y-1 text-sm">
        <p>{external(repoUrl, `${run.owner}/${run.repo}`)}</p>
        <p>
          {g.workflow}: {run.workflow_name}{" "}
          <span className="text-muted">({run.workflow_path})</span>
        </p>
        <p>
          {external(
            run.html_url,
            format(g.run, { number: run.run_number, attempt: run.run_attempt }),
          )}
        </p>
        <p>
          {g.event}: {run.event}
          {run.head_branch && ` · ${g.branch}: ${run.head_branch}`}
        </p>
        <p>
          {g.commit}: {external(`${repoUrl}/commit/${run.head_sha}`, run.head_sha.slice(0, 7))}
        </p>
        <p>
          {g.job}: {external(run.job_html_url, run.job_name)}
        </p>
        {run.failed_steps.length > 0 && (
          <p>
            {g.failedSteps}: {run.failed_steps.join(", ")}
          </p>
        )}
        <p>
          {g.logSource}: {run.log_source === "github" ? g.downloaded : g.pasted}
        </p>
        {run.log_dropped_lines > 0 && (
          <p className="text-muted">{format(g.dropped, { count: run.log_dropped_lines })}</p>
        )}
        <p>
          {g.files}: {run.files_fetched.join(", ")}
        </p>
        {run.files_missing.length > 0 && (
          <p>
            {g.missing}: {run.files_missing.join(", ")}
          </p>
        )}
      </div>
    </section>
  );
}
