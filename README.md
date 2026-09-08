# ATOSScompact

A small ATOSS attendance overlay for Ubuntu/X11. Reads the current Staff Center dashboard and supports the time-recording menu.

## Installation

Copy `installer.sh` into the installation directory, make it executable, and run it as your desktop user:

```bash
chmod +x installer.sh
./installer.sh
```

The installer installs Ubuntu packages and Chrome, clones branch `18+` from `https://github.com/1JuJo/ATOSScompact.git`, prepares `.venv`, generates `run_ATOSScompact.sh`, and creates per-user application and autostart entries. The first debug launch uses **read-only mode** so you can log in and check the overlay without clocking.

For an existing checkout with local changes:

```bash
./installer.sh --skip-clone --skip-launch
```

Options: `--repo-url URL`, `--branch NAME`, `--skip-clone`, `--skip-launch`, and `--non-interactive` (also skips launching). Without `--skip-clone`, installer updates require a clean checkout and a fast-forward merge.

## Running

```bash
./run_ATOSScompact.sh                      # normal use, headless Chrome
./run_ATOSScompact.sh --debug              # visible Chrome for login/troubleshooting
./run_ATOSScompact.sh --debug --read-only  # all attendance actions and hotkeys disabled
```

The runner automatically pulls the current branch's GitHub upstream before each start (`git pull --ff-only`), then installs its runtime requirements. Git failures or a 30-second timeout produce a warning and continue with the local checkout. The runner works from any directory, prevents duplicate launches, and logs to `ATOSScompact.log`. The Chrome login profile stays in `selenium/`.

In normal mode, **Alt+Q+K** or the **Einstempeln** button clocks in; **Alt+Q+G** clocks out / starts a break. These actions affect the real account. Clocking uses the current page status and is submitted once. If ATOSS does not confirm the change, further clocking stays blocked until confirmation arrives; check ATOSS before restarting to try again.

The overlay reads complete dashboard snapshots, removes invisible characters from balances, and supports signed balances exceeding 24 hours. It reconnects after browser/network failures, refreshes stalled attendance data, and shows a grey indicator while data is unavailable. The existing time targets and break calculations are retained.

Global hotkeys require X11. Read-only mode does not start a keyboard listener. If login expires, use `--debug --read-only` to log in again.

## Offline regression check

```bash
.venv/bin/python test_atoss.py
```

Uses fake browser controls and temporary installer output. Covers time calculations, partial data, browser/DNS recovery, stale data, clocking confirmation and duplicate prevention, read-only mode, launcher arguments, auto-update success/failure, dependency installation, and desktop entries. It never opens a real browser or submits attendance.
