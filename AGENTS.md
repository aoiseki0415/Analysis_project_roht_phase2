# Project instructions

## Mandatory startup

- Before every task, read the root `README.md` completely.
- Then read `docs/運用ルール.md` and any analysis-specific document linked from the README.
- Treat the current checked-in documents as the source of truth. If instructions conflict, stop and report the conflict.

## Repository boundary

- Work only in `/Users/aoiseki/GitHub/Analysis_project_roht_phase2`.
- Before every Git write, commit, or push, verify the repository root and confirm that `origin` is exactly `https://github.com/aoiseki0415/Analysis_project_roht_phase2.git`.
- Never operate on another repository, another Git remote, or the SandBox-wide Git account.
- If any deviation from this boundary is detected, stop immediately and notify the user.

## Project folders

- Put active analysis scripts in `解析プログラム/`.
- Move scripts to `解析プログラム（過去版いらなくなったやつ）/` only when they are completely obsolete.
- Use `参考資料（プログラミング関連）/` as a read-only reference unless the user explicitly asks to change it.
- Consult the Gabor-task implementation and the earlier MATLAB analysis when determining data structure, preprocessing steps, behavioral analysis, EEG analysis, ERP, and time-frequency methods.

## Data boundaries

- Treat the Mac desktop raw-data folder as immutable input. Never edit, delete, upload, or commit its contents.
- Write analysis outputs only to the authorized OneDrive `実験本番_本解析` folder. Do not silently fall back to another output directory.
- Use only the authorized Google Drive `実験本解析_Codex共有用` folder, primarily for reference. Do not modify its files unless the user explicitly changes this rule.
- Use and edit only the Notion subtree `研究ワークスペース / SandBox案件_ロート2`.
- Do not put raw data, personal information, or unnecessary participant identifiers in Git, project documentation, Notion, or user-facing summaries.

## Git completion

- Repository edits and operational-document updates must be completed through commit and push without asking for routine approval.
- Stage explicit paths only. Never include unrelated changes such as the existing `.DS_Store` modification.
- Run appropriate checks plus `git diff --cached --check` before committing.
- Report the change to the user only after push succeeds and the remote state has been verified.

## Analysis records

- For every day on which analysis work is performed, update the Notion page `解析の記録` with purpose, data scope, methods, results, interpretation, output location, issues, and next steps.
- Keep observations, interpretations, and hypotheses clearly separated.
