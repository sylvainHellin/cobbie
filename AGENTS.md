# cobbie

## Workflow

- Experiments are run on the home server (`sylvain-home-server`) only, never on the Mac; the Mac just receives the synced `outputs/`.
- Long-running experiments (factorial runs, reruns, judging) MUST be launched inside a `herdr` pane, not `tmux`, so they persist in herdr's background server session after the SSH connection drops. Start one with `herdr agent start <name> --cwd ~/code/tum/cobbie -- <command>`, for example `herdr agent start minimax-rerun --cwd ~/code/tum/cobbie -- bash scripts/run_minimax_rerun.sh`. Monitor it with `herdr agent read <name>` and block on completion with `herdr agent wait <name> --status idle`.

## Project state lives in the Obsidian vault

The single source of truth for this project's state is the Obsidian project note `~/notes/01-projects/1st-journal-paper.md` (in the Mac vault). On any project-level state change (experiment finished, decision taken, section reworked, milestone reached) or when producing a handoff or summary, update that note (curated status + where-we-left-off + next actions) and create or update TaskNotes linked to `[[1st-journal-paper]]` (see the knowledge-base skill). Do not scatter project state across repo `.md` files; repo markdown is for code and experiment-local docs (architecture, dataset, build) only. Long working scratch may live in gitignored `.agents/`, but must be summarized up into the project note and is never the sole record. Keep the project note glanceable, not a dump of full handoffs.
