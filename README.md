# Kensa (検査)

**Kensa investigates failed GitHub Actions runs on your own machine.** It reads the log, gathers
evidence from the log, the repository and a knowledge base, and gives a root-cause diagnosis in
which every claim cites an exact line. A deterministic verifier checks each citation, and checks
separately whether the log actually states the cause. When it cannot tell, Kensa says so instead
of guessing.

It runs on a laptop with a 4 GB GPU, using a local model, and costs nothing to run.

**[Live demo](https://froxily.github.io/kensa/)**: a prerecorded interactive replay in your
browser, not live AI inference · **[Demo video](docs/media/kensa-demo.webm)** (75 s, captioned) ·
**[Source code](https://github.com/froxily/kensa)** · **Docs:** [architecture](ARCHITECTURE.md),
[evaluation](docs/evaluation.md), [testing](docs/testing.md), [security](SECURITY.md)

![A Kensa report from the replay demo: the root cause, its status and the cited source lines](docs/media/report-en.png)

> **Status:** v1.0, milestones M0–M6 complete ([Roadmap](ROADMAP.md)). [Demo video](docs/media/kensa-demo.webm)
> (75 s, captioned; [transcript](docs/media/kensa-demo-transcript.md)) · 日本語の概要は[下記](#日本語概要).
> This repository is a clean snapshot of a private development history, so commit IDs quoted in
> the docs and reports refer to that history.

## Try it without a backend or a model: the replay demo

**[Open the live demo](https://froxily.github.io/kensa/)** (GitHub Pages). It is a
**prerecorded interactive replay, not live AI inference**: a static build of the real UI, showing
**real runs recorded with the local model** (the three built-in samples and three evaluation
cases). No model, backend or database runs behind it. It makes no request outside its own files,
and says on every page that it is a replay. An approval there is kept in the browser tab only and
is labelled as not saved.

The model's output is shown as it was produced, weak parts included. For the test regression,
two of the five proposals would change the test instead of the code, and the one diff that does
fix the code comes with the explanation "No change needed". Kensa shows them as model
suggestions, each with the risk "changing the test instead of the code hides a real regression",
and applies nothing: that is what the human approval step is for.

To build and serve the same replay locally:

```powershell
npm --prefix frontend install
npm --prefix frontend run build:replay
npm --prefix frontend run preview:replay   # http://127.0.0.1:4174
```

![The same report on a phone, in Japanese](docs/media/report-ja-phone.png)

## What Kensa does

```mermaid
flowchart LR
    log["Failed CI log<br/>(paste, upload, or a public GitHub run)"] --> ingest
    ingest["Redact secrets<br/>find error signatures<br/>and stated causes"] --> retrieve
    retrieve["Hybrid retrieval<br/>signatures + full text + vectors<br/>over log, repo, knowledge base"] --> agent
    subgraph agent ["LangGraph agent, checkpointed in PostgreSQL"]
        direction LR
        diagnose["Diagnose<br/>(local model)"] --> verify{"Deterministic<br/>verifier"}
        verify -- "retryable" --> diagnose
        verify --> plan["Plan remediation<br/>(validated diffs)"]
        plan --> report["Save report"]
        report --> approval[/"Human approval<br/>(recorded, never applied)"/]
    end
```

- **Evidence, not eloquence.**
  - Every claim cites a line, and the verifier rejects any citation that does not quote it exactly.
  - Citation validity is shown on its own: genuine citations alone never make a cause "corroborated".
- **An honest status for the root cause:**

  | Status | When |
  |---|---|
  | `corroborated` | A cited log line states a cause of the claimed kind, and nothing in the log points elsewhere |
  | `plausible` | Consistent with the evidence, but the cause is not confirmed |
  | `conflicting` | The evidence points to a different cause |
  | `not established` | Kensa cannot tell, and presents no cause |

  A stated cause (a missing variable, a refused connection or permission) outranks the failing test or build that reports it. A failing test on its own is a symptom, so a test regression is at most `plausible`.
- **Abstains instead of guessing.** If the log does not show the failure, the model is not asked.
- **Deterministic first.** Signature rules and cause patterns do what a rule can do. The model is asked only for what rules cannot do.
- **Human in the loop.**
  - Fix proposals, including diffs that Kensa computes from edits it has checked against the file, are proposals only.
  - Approving records a decision; Kensa never changes a repository.
- **Built to survive failure:**
  - The agent resumes from its last checkpoint after a crash.
  - Jobs use leases, heartbeats, bounded retries and fenced writes in PostgreSQL (no Redis).
  - Each approval decision is recorded exactly once.
- **Read-only GitHub import.** Paste a public repository, run or job URL. Kensa finds the failed job and reads the workflow and the files the log mentions at the run's exact commit.
- **English and Japanese UI,** light and dark, keyboard accessible, checked with axe.

## Results

Measured on one laptop (RTX 3050 Laptop GPU, 4 GB) with `qwen3:4b-instruct-2507`. Two
evaluation sets of synthetic cases were written by a separate LLM author, isolated from Kensa's
code, and frozen before use. Each held-out split
was run once, under a protocol fixed beforehand. Full method and results:
[docs/evaluation.md](docs/evaluation.md).

| Held-out run | Correct root-cause category | Trust |
|---|---|---|
| M5: 20 unseen cases (v1) | 11–13/20 per configuration | Answers labelled "verified" were right only 57–78% of the time. The status model was redesigned |
| M5.1: 60 unseen cases (v2) | **41–44/60** (M5 on the same cases: 28–41) | All 646 accepted citations genuine. But the trust goal was not met: 2–3 wrong answers per configuration were still `corroborated` (M5: 0–1), all of them test failures taken as the cause |
| M5.2 rule | 41–44/60 on those cases, recomputed (one configuration loses one) | A test regression is never `corroborated`. On those 60 cases, recomputed exactly from the stored run, the wrong `corroborated` answers drop to 0. The rule was chosen after seeing them, so this is not a held-out result, and **its effect on new failures is not measured** |

- **Latency:** a diagnosis takes about 13 s at the median with the GPU at full power, and about 20 s when the laptop throttles it.
- **Dev versus held-out:** results on the dev splits were higher than on the held-out splits. The held-out numbers are the ones that count.
- **No held-out data is left:** both test splits are spent, so any further claim needs a new independent set. [docs/evaluation.md](docs/evaluation.md) separates what was measured, what was derived and what is not measured.

## Security and privacy
- **Local only:** the API, the database and the model listen on 127.0.0.1 only. Nothing is sent to a paid or remote service.
- **Secrets are redacted** before a log is stored or shown to the model.
- **Untrusted data:** logs, repository files and model output are treated as data, never executed. Prompt-injection lines are never accepted as evidence.
- **GitHub access is read-only:**
  - Log downloads follow one allowlisted redirect, without credentials, and are refused if the host resolves to a private address.
- **No write path to repositories:** the model has no write tools, and approval only records a decision.
- **Threat model and audit:** [SECURITY.md](SECURITY.md).

## Run it locally

Prerequisites: Docker Desktop, [uv](https://docs.astral.sh/uv/), Node.js 24. For model-based
diagnoses, add [Ollama](https://ollama.com) with `qwen3:4b-instruct-2507-q4_K_M` and
`qwen3-embedding:0.6b`. Without Ollama, choose **Rules only** in the UI.

```powershell
Copy-Item .env.example .env            # then set a local database password
docker compose up -d db
uv sync --directory backend
uv run --directory backend alembic upgrade head
uv run --directory backend uvicorn kensa.main:app --host 127.0.0.1 --port 8000
npm --prefix frontend install
npm --prefix frontend run dev          # http://127.0.0.1:5173
```

## Tests
One command runs every check the CI pipeline runs, locally:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ci-local.ps1
```

| Suite | Count |
|---|---|
| Backend tests (pytest) | 468 |
| Frontend tests (Vitest) | 44 |
| End-to-end tests (Playwright) | 17, including axe in both languages and themes, and the replay build offline, by keyboard and at phone width |

Plus strict mypy, Ruff, ESLint, Prettier and TypeScript checks. See [docs/testing.md](docs/testing.md).

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript (strict), Vite, Tailwind CSS, TanStack Query, React Router |
| Backend | Python 3.13, FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| AI | Ollama (local `qwen3:4b-instruct-2507` and `qwen3-embedding:0.6b`); LangGraph with PostgreSQL checkpoints |
| Data | PostgreSQL 18, pgvector (HNSW), full-text search |
| Quality | pytest, mypy (strict), Ruff, Vitest, Testing Library, Playwright, axe |

## 日本語概要

**Kensa（検査）** は、失敗した GitHub Actions の実行を手元のマシンだけで調査するツールです。CI
のログ、リポジトリのファイル、ナレッジベースから証拠を集め、根本原因の診断を示します。診断の主張には、
すべて根拠となる行（ジョブのログ、リポジトリのファイル、ナレッジベース）への正確な引用が付きます。

- **ローカルで無料:** Ollama 上のローカル LLM（`qwen3:4b-instruct-2507`）と PostgreSQL/pgvector
  で動作します。有料 API やクラウドは使わず、4 GB の GPU を積んだノート PC で動きます。
- **決定論的な検証:**
  - 検証器が、各引用が実在するかを確認し、それとは別に、ログ自体が原因を述べているかを確認します。
  - 「原因の裏付けあり」と表示するのは、ログに原因が記載され、別の原因を示す記述がない場合だけです。
  - 失敗したテストは症状にすぎないため、テストのリグレッションは最大でも「推定（未確認）」です。
- **推測しない:** ログに失敗が示されていなければ、モデルに推測させず「原因を特定できません」と表示します。
- **人による承認:** 修正案（差分を含む）は提案のみです。承認は判断を記録するだけで、リポジトリを変更することはありません。
- **耐障害性:** LangGraph のエージェントは PostgreSQL のチェックポイントから再開でき、ジョブはリースと上限付きの再試行で処理されます。
- **評価:** Kensa のコードから隔離された別の LLM が作成し、使用前に凍結した 60 件の未使用テストケースで、正しいカテゴリを 41〜44 件特定しました。ただし、誤った答え 2〜3 件が「原因の裏付けあり」とされ、信頼性の目標は未達でした。その後の規則（M5.2）は同じ結果を見て決めたため、新しい失敗に対する効果は未測定です。誤りや限界も含めて、結果は [docs/evaluation.md](docs/evaluation.md) にそのまま記載しています。
- **試す:** [ライブデモ](https://froxily.github.io/kensa/)をブラウザーで開けます。これは事前に記録した、操作できるリプレイで、ライブの AI 推論ではありません。バックエンドもモデルも不要な同じリプレイ版（実際の実行の記録）は、上記の `build:replay` でローカルにも作成できます。リプレイ版での承認はブラウザーのタブ内だけに保持され、保存されません。UI は日本語と英語に対応し、スマートフォンの画面幅でも横スクロールせずに表示できます。
- **デモ動画:** 約 1 分 15 秒、音声なし、英語字幕付き（[動画](docs/media/kensa-demo.webm)）。日本語の字幕と書き起こしは [docs/media/kensa-demo-transcript.md](docs/media/kensa-demo-transcript.md) にあります。

## Documentation
- [Architecture](ARCHITECTURE.md) · [Decisions](DECISIONS.md) · [Security](SECURITY.md) · [Roadmap](ROADMAP.md)
- [Evaluation](docs/evaluation.md) · [Testing](docs/testing.md)
- [Licence](LICENSE) (MIT) · [Third-party notices](THIRD_PARTY_NOTICES.md)
