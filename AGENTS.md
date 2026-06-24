# cobbie

## Workflow

- Experiments are run on the home server (`sylvain-home-server`) only, never on the Mac; the Mac just receives the synced `outputs/`.
- Long-running experiments (factorial runs, reruns, judging) MUST be launched inside a `herdr` pane, not `tmux`, so they persist in herdr's background server session after the SSH connection drops. Start one with `herdr agent start <name> --cwd ~/code/tum/cobbie -- <command>`, for example `herdr agent start minimax-rerun --cwd ~/code/tum/cobbie -- bash scripts/run_minimax_rerun.sh`. Monitor it with `herdr agent read <name>` and block on completion with `herdr agent wait <name> --status idle`.
