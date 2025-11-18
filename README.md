# ATOSScompact

## Installation

The project ships with an unattended installer (`installer.sh`) that prepares a fresh Ubuntu workstation, clones the repo, builds the virtual environment, and registers an autostart entry that launches `run_ATOSScompact.sh` (which in turn performs a `git pull` before every start).

1. Create an empty directory on the target machine (for example `~/ATOSScompact`).
2. Copy `installer.sh` into that directory and make it executable.
3. (Optional) Export `REPO_URL`/`REPO_BRANCH` if you want to point at a different remote than the default placeholder.
4. Run the installer; it will ask for sudo once to install `apt` dependencies and Google Chrome.

```bash
mkdir -p ~/ATOSScompact
cp /path/to/installer.sh ~/ATOSScompact/
cd ~/ATOSScompact
chmod +x installer.sh
./installer.sh
```

### What the installer does

- Installs foundational packages: `git`, `python3-venv`, build tools, GNOME desktop helpers, emoji fonts, and the libraries PyQt5/Chrome need.
- Downloads Google Chrome directly from Google if it is not present yet.
- Clones (or updates) the configured Git repository into the directory where the installer resides, preserving the `.git` folder so subsequent launches can `git pull`.
- Sets up `.venv` and installs everything from `requirements.txt`.
- Generates `run_ATOSScompact.sh`, which logs output to `ATOSScompact.log` and performs a safe `git pull` before starting `ATOSScompact.py`.
- Creates `~/.config/autostart/ATOSScompact.desktop` so GNOME automatically starts the app in a terminal window on login.
- Launches `run_ATOSScompact.sh --debug` once after setup so you can immediately verify that the UI is working.

## Manual usage

`run_ATOSScompact.sh` is the launch script used by the autostart entry. You can also invoke it manually:

```bash
./run_ATOSScompact.sh          # headless Chrome (default)
./run_ATOSScompact.sh --debug  # show Chrome/UI for troubleshooting
```

All additional arguments are forwarded to `ATOSScompact.py`, so `./run_ATOSScompact.sh --debug --foo bar` behaves the same as running the Python file directly. Logs always end up in `ATOSScompact.log` regardless of where the script is invoked from.

If something goes wrong (for example, a `git pull` cannot fast-forward), check `ATOSScompact.log` or rerun `installer.sh` to remediate.
