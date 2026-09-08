"""Offline regression check: .venv/bin/python test_atoss.py (no real browser or clocking)."""
import fcntl
import importlib.metadata
import logging
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from unittest.mock import Mock, patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import ATOSScompact as atoss
atoss.logger.setLevel(logging.ERROR)


def check():
    sample = {
        'Status': 'Anwesend', 'Heutige Anwesenheit': '5:02', 'Heutige Pause': '0:00',
        'Kommen': '08:15', 'Gehen': 'k.A.', 'Arbeitszeitkonto': '-\u200b62:15',
    }
    assert atoss.TimeUtils.add_times('-\u200b62:15', '-2:40') == '-64:55'
    assert atoss.TimeUtils.subtract_times('+125:00', '-0:30') == '125:30'
    assert atoss.TimeUtils.add_times('−0:30', '0:30') == '00:00'
    for bad in ('bad', '12:60', '1:2', '', '1:-30'):
        try:
            atoss.TimeUtils.to_minutes(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Accepted malformed time: {bad}')

    controller = atoss.BrowserController()
    driver = Mock()
    controller.driver = driver
    driver.execute_script.return_value = sample.copy()
    data = controller._read_data()
    assert data['Arbeitszeitkonto'] == '-62:15'
    driver.find_element.assert_called_with(atoss.By.ID, 'applicationIframe')
    driver.switch_to.default_content.assert_called()
    lines = atoss.DataProcessor.format_display_data(data)
    assert '-62:15 (-64:58)' in lines[-1]
    assert '14:15/16:27/17:45' in lines[3]
    overnight = dict(data, Kommen='22:15')
    assert '04:15/06:27/07:45' in atoss.DataProcessor.format_display_data(overnight)[3]
    absent = dict.fromkeys(sample, 'k.A.')
    absent['Status'] = 'Abwesend'
    assert len(atoss.DataProcessor.format_display_data(absent)) == 4
    driver.execute_script.return_value = {'Status': 'Abwesend'}
    try:
        controller._read_data()
    except ValueError:
        pass
    else:
        raise AssertionError('Partial dashboard was accepted')

    # Neither a failed browser start nor DNS failure may disable future retries.
    controller.driver = None
    starts = []

    def init_driver():
        starts.append(True)
        if len(starts) == 1:
            raise atoss.WebDriverException('Browser startup failed')
        controller.driver = driver

    def next_poll(seconds):
        if driver.get.call_count == 2:
            controller.running = False
        assert len(starts) <= 3, 'Recovery is stuck'

    driver.get.side_effect = [atoss.WebDriverException('net::ERR_NAME_NOT_RESOLVED'), None]
    driver.execute_script.return_value = data.copy()
    with patch.object(controller, '_init_driver', side_effect=init_driver), patch.object(atoss.time, 'sleep', side_effect=next_poll):
        controller._monitor()
    assert len(starts) == 3 and controller.loaded
    assert all(call.args[0].endswith('/html?security.sso=true') for call in driver.get.call_args_list)
    driver.quit.assert_called_once()
    driver.get.side_effect = None

    # A stale rendered page must trigger a refresh even though reading its DOM succeeds.
    controller.last_reload = 100
    controller.antidesync_time = 100
    with patch.object(atoss.time, 'monotonic', return_value=191):
        controller._poll()
    assert not controller.loaded and not controller.extracted_data
    with patch.object(atoss.time, 'monotonic', return_value=222):
        controller._poll()
    assert controller.loaded, 'Unloaded state must recover'

    # ChromeDriver can die below Selenium's exception layer; cleanup can fail too.
    controller.running = True
    driver.execute_script.side_effect = [atoss.HTTPError('Connection lost'), data.copy()]
    driver.quit.side_effect = atoss.HTTPError('Driver already stopped')
    def finish_reconnect(seconds):
        if controller.loaded:
            controller.running = False
        assert len(starts) <= 4, 'Driver connection did not recover'
    with patch.object(controller, '_init_driver', side_effect=init_driver), patch.object(atoss.time, 'sleep', side_effect=finish_reconnect):
        controller._monitor()
    assert controller.loaded and len(starts) == 4

    # Every clocking operation below uses this fake driver. Chrome is also blocked at entry.
    for is_break in (False, True):
        for result in ('confirmed', 'unconfirmed', 'click_error', 'wrong_status', 'changed_status', 'read_only', 'not_loaded', 'busy', 'menu'):
            controller = atoss.BrowserController(read_only=result == 'read_only')
            controller.loaded = result != 'not_loaded'
            driver = Mock()
            controller.driver = driver
            before = dict(data, Status='Anwesend' if is_break else 'Abwesend')
            after = dict(before, Status='Abwesend' if is_break else 'Anwesend')
            driver.execute_script.return_value = after if result == 'wrong_status' else before
            if result == 'changed_status':
                driver.execute_script.side_effect = [before, after]
            button = Mock()
            button.get_attribute.return_value = None
            driver.find_elements.return_value = [button]
            if result == 'menu':
                menu = Mock()
                menu.get_attribute.return_value = None
                driver.find_elements.side_effect = [[], [menu], [button]]
            if result == 'click_error':
                button.click.side_effect = atoss.WebDriverException('Reply lost')
            elif result in ('confirmed', 'menu'):
                button.click.side_effect = lambda: setattr(driver.execute_script, 'return_value', after)
            if result == 'busy':
                controller.stamp_lock.acquire()
            messages = []
            controller.update_msg.connect(messages.append)

            def wait_once(predicate):
                value = predicate(driver)
                if not value:
                    raise atoss.TimeoutException('No confirmation')
                return value

            with patch.object(atoss, 'WebDriverWait') as wait:
                wait.return_value.until.side_effect = wait_once
                controller.stempeln(is_break)
            if result in ('confirmed', 'unconfirmed', 'click_error', 'menu'):
                button.click.assert_called_once()
                if result in ('confirmed', 'menu'):
                    assert controller.loaded and controller.extracted_data['Status'] == after['Status']
                else:
                    assert any('unklar' in message for message in messages)
                    try:
                        controller._publish_data(before)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('Unconfirmed clocking was accepted')
                    controller.stempeln(is_break)
                    button.click.assert_called_once()
                    controller._publish_data(after)
                    assert controller.loaded and controller.pending_status is None
            else:
                button.click.assert_not_called()
            if result != 'busy':
                assert not controller.stamp_lock.locked()

    app = atoss.QApplication.instance() or atoss.QApplication([])
    window = atoss.OverlayWindow()
    window.update_status('Abwesend', lines)
    assert not window.clock_button.isHidden()
    window.set_message('Verbindung unterbrochen')
    assert window.clock_button.isHidden() and window.circle.color == atoss.QColor(atoss.Qt.gray)
    window.close()
    app.processEvents()

    root = Path(__file__).resolve().parent
    for line in (root / 'requirements.txt').read_text().splitlines():
        if line and not line.startswith('#'):
            name, version = line.split('==')
            assert importlib.metadata.version(name) == version
    subprocess.run(['bash', '-n', str(root / 'installer.sh')], check=True)
    for option in ('--branch', '--repo-url'):
        assert subprocess.run(['bash', str(root / 'installer.sh'), option], capture_output=True).returncode != 0
    with tempfile.TemporaryDirectory(prefix='atoss offline checks ') as directory:
        dest = Path(directory)
        script = f'''source {shlex.quote(str(root / 'installer.sh'))}
INSTALL_DIR={shlex.quote(directory)}
RUNNER_PATH="$INSTALL_DIR/run_ATOSScompact.sh"
AUTOSTART_DIR="$INSTALL_DIR/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/ATOSScompact.desktop"
SYSTEM_DESKTOP_FILE="$INSTALL_DIR/applications/ATOSScompact.desktop"
create_runner_script
configure_autostart
install_system_desktop_entry
'''
        subprocess.run(['bash', '-c', script], check=True, capture_output=True)
        runner = dest / 'run_ATOSScompact.sh'
        assert subprocess.run([str(runner)], capture_output=True).returncode == 1
        python = dest / '.venv/bin/python3'
        python.parent.mkdir(parents=True)
        python.write_text('''#!/bin/sh
if [ "$1" = -m ]; then
    printf '%s\\n' "$@" > "$ATOSS_TEST_PIP_ARGS"
    exit "${ATOSS_TEST_PIP_STATUS:-0}"
fi
printf '%s\\n' "$@" > "$ATOSS_TEST_ARGS"
''')
        python.chmod(0o755)
        args = dest / 'args'
        pip_args = dest / 'pip-args'
        env = dict(os.environ, ATOSS_TEST_ARGS=str(args), ATOSS_TEST_PIP_ARGS=str(pip_args))
        subprocess.run([str(runner), '--read-only'], cwd='/tmp', env=env, check=True, capture_output=True)
        assert args.read_text().splitlines() == ['ATOSScompact.py', '--read-only']
        assert pip_args.read_text().splitlines() == ['-m', 'pip', 'install', '--disable-pip-version-check', '-r', str(dest / 'requirements.txt')]

        # Fake Git keeps every update check offline and leaves the working repository untouched.
        git = dest / 'bin/git'
        git.parent.mkdir()
        git.write_text('''#!/bin/sh
printf '%s\\n' "$@" > "$ATOSS_TEST_GIT_ARGS"
[ "$GIT_TERMINAL_PROMPT" = 0 ] || exit 99
exit "$ATOSS_TEST_GIT_STATUS"
''')
        git.chmod(0o755)
        (dest / '.git').touch()
        git_args = dest / 'git-args'
        env.update(PATH=str(git.parent) + os.pathsep + env['PATH'], ATOSS_TEST_GIT_ARGS=str(git_args))
        for status in ('0', '1', '124'):
            args.unlink()
            env['ATOSS_TEST_GIT_STATUS'] = status
            result = subprocess.run([str(runner), '--read-only'], env=env, check=True, capture_output=True, text=True)
            assert git_args.read_text().splitlines() == ['-C', directory, 'pull', '--ff-only']
            assert ('Git auto-update failed' in result.stdout) == (status != '0')
            assert args.read_text().splitlines() == ['ATOSScompact.py', '--read-only']
        env['ATOSS_TEST_PIP_STATUS'] = '1'
        args.unlink()
        assert subprocess.run([str(runner)], env=env, capture_output=True).returncode != 0
        assert not args.exists(), 'Started app after dependency installation failed'
        env['ATOSS_TEST_PIP_STATUS'] = '0'
        subprocess.run([str(runner)], env=env, check=True, capture_output=True)
        args.unlink()
        with (dest / '.ATOSScompact.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            subprocess.run([str(runner)], env=env, check=True, capture_output=True)
            assert not args.exists(), 'Second instance started'
        if shutil.which('desktop-file-validate'):
            for desktop in dest.glob('*/*.desktop'):
                subprocess.run(['desktop-file-validate', str(desktop)], check=True)
    print('All offline checks passed; no real browser or attendance actions were used.')


if __name__ == '__main__':
    with patch.object(atoss.webdriver, 'Chrome', side_effect=AssertionError('Real browsers are forbidden in this check')):
        check()
