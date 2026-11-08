# Demo video: transcript

[kensa-demo.webm](kensa-demo.webm) is about 75 seconds long and has no sound. It was captured by `npm --prefix frontend run media` from the replay build, which shows 6 runs recorded with the local model. The English captions are part of the picture. The same captions, with timings, are in [kensa-demo.en.vtt](kensa-demo.en.vtt) and, in Japanese, [kensa-demo.ja.vtt](kensa-demo.ja.vtt).

動画には音声がありません。英語の字幕は映像に含まれています。日本語の字幕は kensa-demo.ja.vtt と下の表にあります。

| Time | Caption | 字幕 |
|---|---|---|
| 00:00 | A replay of 6 real Kensa runs, recorded with a local model (qwen3:4b) on a 4 GB laptop GPU. Nothing is running now. | 4 GB のノート PC 向け GPU 上のローカルモデル（qwen3:4b）で記録した、Kensa の実際の実行 6 件のリプレイです。現在は何も実行されていません。 |
| 00:08 | A built-in sample: "Frontend build fails an environment check". | 組み込みサンプル：「Frontend build fails an environment check」 |
| 00:12 | Every claim cites a source line. The verifier found 4 of 4 quotes on their cited lines (1 in the job log, 3 in knowledge-base notes), and the log itself states the cause: "Cause corroborated". | すべての主張は根拠となる行を引用します。検証器は 4 件中 4 件の引用を引用先の行で確認しました（ジョブログ 1 件、ナレッジベース 3 件）。ログ自体に原因が記載されているため「原因の裏付けあり」です。 |
| 00:26 | A citation of the log opens its line in the stored log; other citations open their evidence excerpt. | ログの引用は保存されたログの該当行を開き、それ以外の引用は該当する証拠の抜粋を開きます。 |
| 00:33 | Fixes are proposals only. Kensa never changes a repository. | 修正は提案のみです。Kensa がリポジトリを変更することはありません。 |
| 00:37 | In the replay, a decision is kept in this browser tab only. Nothing is saved. | リプレイでは、判断はこのブラウザーのタブ内でのみ保持され、保存されません。 |
| 00:43 | A failing test is a symptom, so a test regression is at most "Plausible, not confirmed". | 失敗したテストは症状にすぎないため、テストのリグレッションは最大でも「推定（未確認）」です。 |
| 00:49 | The model's proposals are shown as produced, mistakes included: 2 of the 5 would change the test instead of the code. Each carries the risk that this hides a real regression. | モデルの提案は誤りも含めて生成されたまま表示されます。5 件中 2 件はコードではなくテストを変更する提案です。どの提案にも、それが本当のリグレッションを隠しうるというリスクが示されています。 |
| 01:01 | This log does not show the failure, so Kensa does not ask the model to guess: "Not established". | このログには失敗が示されていないため、Kensa はモデルに推測させません（「特定できず」）。 |
| 01:08 | The interface is also in Japanese. Recorded model output stays in English. | UI は日本語にも対応しています。記録されたモデルの出力は英語のままです。 |
