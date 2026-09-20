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
- The copied Google Drive spreadsheets have been de-identified and may be inspected without routine approval. Use participant IDs internally only as needed for matching and analysis; do not disclose or persist them unnecessarily.
- Use and edit only the Notion subtree `研究ワークスペース / SandBox案件_ロート2`.
- Do not put raw data, personal information, or unnecessary participant identifiers in Git, project documentation, Notion, or user-facing summaries.

## Git completion

- Repository edits and operational-document updates must be completed through commit and push without asking for routine approval.
- Stage explicit paths only. Never include unrelated changes such as the existing `.DS_Store` modification.
- Run appropriate checks plus `git diff --cached --check` before committing.
- Report the change to the user only after push succeeds and the remote state has been verified.

## Analysis records

- For every day on which analysis work is performed, update the Notion page `解析の記録` with purpose, data scope, methods, results, interpretation, output location, issues, and next steps.
- When repository changes are part of the work, add the verified Git commit hash and a brief description to the corresponding Notion analysis record after push succeeds.
- Keep observations, interpretations, and hypotheses clearly separated.
- When a standing operating rule, analysis decision, or project-wide assumption is established, update the relevant checked-in document and the corresponding Notion page during the same task without waiting for a separate request.
- After any repository documentation or script change, complete validation, commit, push, and remote verification before reporting completion.

## Implementation environment

- Implement the new analysis pipeline in Python, not MATLAB.
- Treat the existing MATLAB scripts as methodological references only.
- Do not use Apple's Command Line Tools Python as the project runtime.
- Read `docs/Python環境.md` before changing or running Python code.
- Use the locked project environment: Python 3.14.7 in `.venv`, managed by the repository-local `.tools/uv/uv`.
- Keep active analysis scripts in `解析プログラム/`, run checks before commit, and never commit `.venv/` or `.tools/`.
