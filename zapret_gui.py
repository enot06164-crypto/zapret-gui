import os
import sys
import re
import glob
import json
import shutil
import zipfile
import secrets
import threading
import subprocess
import time
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response

if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = SCRIPT_DIR

CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config.json')
_DEFAULT_CONFIG = {'zapret_dir': r'C:\zapret', 'font_size': 14}


def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        for k, v in _DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except Exception:
        return dict(_DEFAULT_CONFIG)


def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


_config = load_config()
ZAPRET_DIR = _config['zapret_dir']
_NO_WINDOW = subprocess.CREATE_NO_WINDOW


def _update_dirs():
    global BIN_DIR, LISTS_DIR, UTILS_DIR, RESULTS_DIR
    BIN_DIR = os.path.join(ZAPRET_DIR, 'bin')
    LISTS_DIR = os.path.join(ZAPRET_DIR, 'lists')
    UTILS_DIR = os.path.join(ZAPRET_DIR, 'utils')
    RESULTS_DIR = os.path.join(UTILS_DIR, 'test results')


_update_dirs()

GITHUB_REPO = 'Flowseal/zapret-discord-youtube'
GITHUB_VERSION_URL = 'https://raw.githubusercontent.com/' + GITHUB_REPO + '/main/.service/version.txt'
GITHUB_API_RELEASES = 'https://api.github.com/repos/' + GITHUB_REPO + '/releases/latest'

app = Flask(__name__, template_folder=os.path.join(BUNDLE_DIR, 'templates'), static_folder=os.path.join(BUNDLE_DIR, 'static'))
CSRF_TOKEN = secrets.token_hex(32)
download_progress = {'percent': 0, 'status': 'idle', 'message': ''}
_download_lock = threading.Lock()
_file_locks = {}
_file_locks_lock = threading.Lock()


def update_progress(percent=None, status=None, message=None):
    with _download_lock:
        if percent is not None:
            download_progress['percent'] = percent
        if status is not None:
            download_progress['status'] = status
        if message is not None:
            download_progress['message'] = message


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if origin.startswith('chrome-extension://') or origin.startswith('moz-extension://'):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

def check_csrf():
    if request.method == 'POST':
        token = request.headers.get('X-CSRF-Token', '')
        if token != CSRF_TOKEN:
            return jsonify({'error': 'Invalid CSRF token'}), 403
    return None


ALLOWED_LISTS = {
    'list-general': 'list-general.txt',
    'list-general-user': 'list-general-user.txt',
    'list-exclude': 'list-exclude.txt',
    'list-exclude-user': 'list-exclude-user.txt',
    'ipset-all': 'ipset-all.txt',
    'ipset-exclude': 'ipset-exclude.txt',
    'ipset-exclude-user': 'ipset-exclude-user.txt',
    'list-google': 'list-google.txt',
}

ACTIVE_STRATEGY_FILE = os.path.join(UTILS_DIR, '.active_strategy')
GAME_FLAG_FILE = os.path.join(UTILS_DIR, 'game_filter.enabled')
UPDATE_FLAG_FILE = os.path.join(UTILS_DIR, 'check_updates.enabled')


def is_zapret_installed():
    return os.path.isdir(ZAPRET_DIR) and os.path.isfile(os.path.join(BIN_DIR, 'winws.exe'))


def get_file_lock(filepath):
    with _file_locks_lock:
        if filepath not in _file_locks:
            _file_locks[filepath] = threading.Lock()
        return _file_locks[filepath]


def get_local_version():
    version_file = os.path.join(ZAPRET_DIR, '.service', 'version.txt')
    try:
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except Exception:
        pass
    bat_file = os.path.join(ZAPRET_DIR, 'service.bat')
    try:
        if os.path.exists(bat_file):
            with open(bat_file, 'r', encoding='utf-8') as f:
                for line in f:
                    m = re.search(r'set\s+"LOCAL_VERSION=([^"]+)"', line)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    return None


def check_github_version():
    try:
        import urllib.request
        req = urllib.request.Request(GITHUB_VERSION_URL, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8').strip()
    except Exception:
        return None


def get_github_release_info():
    try:
        import urllib.request
        req = urllib.request.Request(GITHUB_API_RELEASES, headers={
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'zapret-gui'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            zip_url = None
            for asset in data.get('assets', []):
                if asset.get('name', '').endswith('.zip'):
                    zip_url = asset['browser_download_url']
                    break
            return {
                'tag': data.get('tag_name', ''),
                'name': data.get('name', ''),
                'zip_url': zip_url,
            }
    except Exception:
        return None


def download_file(url, dest):
    global download_progress
    try:
        import urllib.request
        def report(block, block_size, total_size):
            if total_size and total_size > 0:
                downloaded = block * block_size
                pct = min(int(downloaded * 100 / total_size), 100)
                download_progress['percent'] = pct
                download_progress['message'] = str(pct) + '% (' + str(downloaded // 1024) + ' / ' + str(total_size // 1024) + ' KB)'
        urllib.request.urlretrieve(url, dest, reporthook=report)
        return True
    except Exception as e:
        download_progress['status'] = 'error'
        download_progress['message'] = str(e)
        return False


def extract_zip_to(tmp_zip, target_dir, version_tag=''):
    global download_progress
    update_progress(percent=100, status='extracting', message='Extracting...')
    tmp_dir = target_dir + '_tmp_extract'
    try:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)
        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            members = zf.namelist()
            if members:
                common_prefix = os.path.commonprefix(members)
                if common_prefix and not common_prefix.endswith('/'):
                    common_prefix = os.path.dirname(common_prefix) + '/'
                for member in members:
                    if common_prefix:
                        rel = member[len(common_prefix):] if member.startswith(common_prefix) else member
                    else:
                        rel = member
                    if rel:
                        target = os.path.realpath(os.path.join(tmp_dir, rel))
                        if not target.startswith(os.path.realpath(tmp_dir)):
                            raise ValueError('Zip entry ' + member + ' escapes target directory')
                        if member.endswith('/'):
                            os.makedirs(target, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(target), exist_ok=True)
                            with zf.open(member) as src, open(target, 'wb') as dst:
                                shutil.copyfileobj(src, dst)
        if version_tag:
            ver_dir = os.path.join(tmp_dir, '.service')
            os.makedirs(ver_dir, exist_ok=True)
            with open(os.path.join(ver_dir, 'version.txt'), 'w', encoding='utf-8') as f:
                f.write(version_tag)
        if os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
        os.rename(tmp_dir, target_dir)
    except Exception as e:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        update_progress(percent=0, status='error', message='Extraction failed: ' + str(e))
        return False
    return True


def do_download_install():
    global download_progress
    update_progress(percent=0, status='downloading', message='Fetching release info...')
    release = get_github_release_info()
    if not release or not release.get('zip_url'):
        update_progress(percent=0, status='error', message='Failed to get release info from GitHub')
        return False
    download_progress['message'] = 'Downloading ' + release.get('name', release.get('tag', '')) + '...'
    tmp_zip = os.path.join(SCRIPT_DIR, 'zapret_tmp.zip')
    if not download_file(release['zip_url'], tmp_zip):
        return False
    if not extract_zip_to(tmp_zip, ZAPRET_DIR, release.get('tag', '')):
        return False
    if os.path.exists(tmp_zip):
        try:
            os.remove(tmp_zip)
        except Exception:
            pass
    update_progress(percent=100, status='done', message='Installed successfully')
    return True


def do_download_update():
    global download_progress
    update_progress(percent=0, status='downloading', message='Stopping zapret...')
    try:
        subprocess.run(['taskkill', '/IM', 'winws.exe', '/F'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        subprocess.run(['net', 'stop', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        time.sleep(1)
    except Exception:
        pass
    update_progress(percent=5, status='downloading', message='Fetching release info...')
    release = get_github_release_info()
    if not release or not release.get('zip_url'):
        update_progress(percent=0, status='error', message='Failed to get release info from GitHub')
        return False
    download_progress['message'] = 'Downloading ' + release.get('name', release.get('tag', '')) + '...'
    tmp_zip = os.path.join(SCRIPT_DIR, 'zapret_tmp.zip')
    if not download_file(release['zip_url'], tmp_zip):
        return False
    if not extract_zip_to(tmp_zip, ZAPRET_DIR, release.get('tag', '')):
        return False
    if os.path.exists(tmp_zip):
        try:
            os.remove(tmp_zip)
        except Exception:
            pass
    update_progress(percent=100, status='done', message='Updated successfully')
    return True


def get_bat_files():
    files = glob.glob(os.path.join(ZAPRET_DIR, 'general*.bat'))
    files = [f for f in files if 'service' not in os.path.basename(f).lower()]
    def sort_key(path):
        name = os.path.basename(path)
        nums = re.findall(r'\d+', name)
        return (len(nums), int(nums[0]) if nums else 0, name)
    files.sort(key=sort_key)
    return files


def get_current_strategy():
    try:
        result = subprocess.run(
            ['reg', 'query', r'HKLM\System\CurrentControlSet\Services\zapret', '/v', 'zapret-discord-youtube'],
            capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if 'zapret-discord-youtube' in line:
                    parts = line.split('REG_SZ')
                    if len(parts) > 1:
                        return parts[1].strip()
    except Exception:
        pass
    if os.path.exists(ACTIVE_STRATEGY_FILE):
        try:
            with open(ACTIVE_STRATEGY_FILE, 'r', encoding='utf-8') as f:
                strategy = f.read().strip()
            if strategy and is_winws_running():
                return strategy
        except Exception:
            pass
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq winws.exe', '/V', '/FO', 'CSV'],
            capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if 'winws.exe' in line.lower():
                    m = re.search(r'zapret:\s*"?([^",]+)', line)
                    if m:
                        return m.group(1).strip().strip('"')
    except Exception:
        pass
    return None


def is_winws_running():
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq winws.exe'],
            capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
        )
        return 'winws.exe' in result.stdout.lower()
    except Exception:
        return False


def get_service_status(name='zapret'):
    try:
        result = subprocess.run(
            ['sc', 'query', name],
            capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
        )
        if result.returncode != 0:
            return 'NOT_INSTALLED'
        for line in result.stdout.splitlines():
            if 'STATE' in line.upper():
                upper = line.upper()
                if 'RUNNING' in upper:
                    return 'RUNNING'
                elif 'STOPPED' in upper:
                    return 'STOPPED'
                elif 'STOP_PENDING' in upper:
                    return 'STOP_PENDING'
        return 'UNKNOWN'
    except Exception:
        return 'UNKNOWN'


def get_game_filter():
    if not os.path.exists(GAME_FLAG_FILE):
        return 'disabled'
    try:
        with open(GAME_FLAG_FILE, 'r') as f:
            mode = f.read().strip().lower()
        if mode in ('all', 'tcp', 'udp'):
            return mode
    except Exception:
        pass
    return 'disabled'


def get_ipset_status():
    list_file = os.path.join(LISTS_DIR, 'ipset-all.txt')
    try:
        if not os.path.exists(list_file):
            return 'none'
        with open(list_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) == 0:
            return 'any'
        if any('203.0.113.113/32' in line for line in lines):
            return 'none'
        return 'loaded'
    except Exception:
        return 'unknown'


def get_update_status():
    return 'enabled' if os.path.exists(UPDATE_FLAG_FILE) else 'disabled'


@app.route('/')
def index():
    return render_template('index.html', csrf_token=CSRF_TOKEN)


@app.route('/api/setup/status')
def api_setup_status():
    return jsonify({
        'installed': is_zapret_installed(),
        'path': ZAPRET_DIR,
        'version': get_local_version() if is_zapret_installed() else None,
    })


@app.route('/api/setup/download', methods=['POST'])
def api_setup_download():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    global download_progress
    with _download_lock:
        if download_progress.get('status') in ('downloading', 'extracting'):
            return jsonify({'error': 'Download already in progress'}), 409
        mode = (request.get_json() or {}).get('mode', 'install')
        if mode == 'update':
            thread = threading.Thread(target=do_download_update, daemon=True)
        else:
            thread = threading.Thread(target=do_download_install, daemon=True)
        thread.start()
    return jsonify({'success': True, 'message': 'Download started'})


@app.route('/api/setup/progress')
def api_setup_progress():
    def generate():
        last = ''
        for _ in range(600):
            current = json.dumps(download_progress)
            if current != last:
                yield 'data: ' + current + '\n\n'
                last = current
            if download_progress.get('status') in ('done', 'error'):
                break
            time.sleep(0.5)
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/setup/update-check')
def api_setup_update_check():
    local = get_local_version()
    remote = check_github_version()
    if not remote:
        return jsonify({'update_available': False, 'error': 'Could not check GitHub'})
    if not local:
        return jsonify({'update_available': False, 'local_version': None, 'remote_version': remote})
    return jsonify({
        'update_available': local != remote,
        'local_version': local,
        'remote_version': remote,
    })


@app.route('/api/setup/detect')
def api_setup_detect():
    found = []
    checked = set()
    for pattern in [r'C:\zapret', r'C:\zapret-*', r'C:\zapret_*']:
        for match in glob.glob(pattern):
            if not os.path.isdir(match) or match in checked:
                continue
            checked.add(match)
            winws = os.path.join(match, 'bin', 'winws.exe')
            if os.path.isfile(winws):
                version = None
                vfile = os.path.join(match, '.service', 'version.txt')
                try:
                    if os.path.exists(vfile):
                        with open(vfile, 'r', encoding='utf-8') as f:
                            version = f.read().strip()
                except Exception:
                    pass
                if not version:
                    bfile = os.path.join(match, 'service.bat')
                    try:
                        if os.path.exists(bfile):
                            with open(bfile, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if 'winws.exe' in line:
                                        m = re.search(r'--version\s+(\S+)', line)
                                        if m:
                                            version = m.group(1)
                                        break
                    except Exception:
                        pass
                found.append({'path': match, 'version': version})
    found.sort(key=lambda x: x['path'])
    return jsonify({'found': found, 'current': ZAPRET_DIR})


@app.route('/api/setup/select', methods=['POST'])
def api_setup_select():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    data = request.get_json() or {}
    path = data.get('path', '').strip().rstrip('\\')
    if not path:
        return jsonify({'error': 'Path is required'}), 400
    if not os.path.isdir(path):
        return jsonify({'error': 'Directory does not exist'}), 400
    winws = os.path.join(path, 'bin', 'winws.exe')
    if not os.path.isfile(winws):
        return jsonify({'error': 'winws.exe not found in ' + path + '\\bin'}), 400
    global ZAPRET_DIR, _config
    ZAPRET_DIR = path
    _config['zapret_dir'] = path
    save_config(_config)
    _update_dirs()
    return jsonify({'success': True, 'path': path, 'version': get_local_version()})


@app.route('/api/status')
def api_status():
    if not is_zapret_installed():
        return jsonify({'installed': False})
    winws_running = is_winws_running()
    service_status = get_service_status('zapret')
    windivert_status = get_service_status('WinDivert')
    strategy = get_current_strategy()
    game_filter = get_game_filter()
    ipset_status = get_ipset_status()
    update_status = get_update_status()
    bat_files = get_bat_files()
    active_bat = None
    if strategy:
        for f in bat_files:
            if os.path.basename(f).replace('.bat', '') == strategy:
                active_bat = os.path.basename(f)
                break
    return jsonify({
        'installed': True,
        'winws_running': winws_running,
        'service_status': service_status,
        'windivert_status': windivert_status,
        'strategy': strategy,
        'active_bat': active_bat,
        'game_filter': game_filter,
        'ipset_status': ipset_status,
        'update_status': update_status,
        'zapret_dir': ZAPRET_DIR,
        'version': get_local_version(),
    })


@app.route('/api/strategies')
def api_strategies():
    if not is_zapret_installed():
        return jsonify([])
    files = get_bat_files()
    current = get_current_strategy()
    result = []
    for f in files:
        name = os.path.basename(f).replace('.bat', '')
        result.append({
            'name': name,
            'filename': os.path.basename(f),
            'path': f,
            'active': name == current,
        })
    return jsonify(result)


@app.route('/api/start', methods=['POST'])
def api_start():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    bat_name = data.get('bat')
    if not bat_name:
        return jsonify({'error': 'No bat file specified'}), 400
    bat_path = os.path.realpath(os.path.join(ZAPRET_DIR, bat_name))
    if not bat_path.startswith(os.path.realpath(ZAPRET_DIR)):
        return jsonify({'error': 'Invalid bat file'}), 400
    if not os.path.exists(bat_path):
        return jsonify({'error': 'File not found: ' + bat_name}), 404
    subprocess.run(['taskkill', '/IM', 'winws.exe', '/F'], capture_output=True, creationflags=_NO_WINDOW)
    time.sleep(1)
    subprocess.Popen(
        ['cmd.exe', '/c', bat_path],
        cwd=ZAPRET_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW,
        start_new_session=True
    )
    time.sleep(2)
    running = is_winws_running()
    if running:
        strategy_name = bat_name.replace('.bat', '')
        try:
            os.makedirs(UTILS_DIR, exist_ok=True)
            with open(ACTIVE_STRATEGY_FILE, 'w', encoding='utf-8') as f:
                f.write(strategy_name)
        except Exception:
            pass
    return jsonify({'success': running, 'message': 'Started' if running else 'Failed to start'})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    try:
        subprocess.run(['net', 'stop', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        time.sleep(1)
        subprocess.run(['taskkill', '/IM', 'winws.exe', '/F'], capture_output=True, timeout=5, creationflags=_NO_WINDOW)
        time.sleep(2)
        running = is_winws_running()
        if not running and os.path.exists(ACTIVE_STRATEGY_FILE):
            os.remove(ACTIVE_STRATEGY_FILE)
        return jsonify({'success': not running, 'message': 'Stopped' if not running else 'Failed to stop'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/service/install', methods=['POST'])
def api_service_install():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    bat_name = data.get('bat')
    if not bat_name:
        return jsonify({'error': 'No bat file specified'}), 400
    bat_path = os.path.realpath(os.path.join(ZAPRET_DIR, bat_name))
    if not bat_path.startswith(os.path.realpath(ZAPRET_DIR)):
        return jsonify({'error': 'Invalid bat file'}), 400
    if not os.path.exists(bat_path):
        return jsonify({'error': 'File not found: ' + bat_name}), 404
    winws_exe = os.path.join(BIN_DIR, 'winws.exe')
    try:
        subprocess.run(['net', 'stop', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        subprocess.run(['sc', 'delete', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        time.sleep(1)
        args = build_service_args(bat_path)
        bin_path = '"' + winws_exe + '" ' + args
        subprocess.run(
            ['sc', 'create', 'zapret', 'binPath= ' + bin_path, 'DisplayName= zapret', 'start= auto'],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW
        )
        subprocess.run(['sc', 'description', 'zapret', 'Zapret DPI bypass software'],
                       capture_output=True, timeout=5, creationflags=_NO_WINDOW)
        subprocess.run(['net', 'start', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        strategy_name = bat_name.replace('.bat', '')
        subprocess.run(
            ['reg', 'add', r'HKLM\System\CurrentControlSet\Services\zapret',
             '/v', 'zapret-discord-youtube', '/t', 'REG_SZ', '/d', strategy_name, '/f'],
            capture_output=True, timeout=5, creationflags=_NO_WINDOW
        )
        return jsonify({'success': True, 'message': 'Service installed with ' + bat_name})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def build_service_args(bat_path):
    try:
        with open(bat_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return ''
    args = []
    for line in content.splitlines():
        line = line.strip()
        if 'winws.exe' not in line.lower():
            continue
        line = line.replace('^', '')
        parts = line.split()
        for part in parts:
            if 'winws.exe' in part.lower():
                continue
            if ' ' in part and not (part.startswith('"') and part.endswith('"')):
                args.append('"' + part + '"')
            else:
                args.append(part)
        break
    return ' '.join(args)


@app.route('/api/service/remove', methods=['POST'])
def api_service_remove():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    try:
        subprocess.run(['net', 'stop', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        subprocess.run(['sc', 'delete', 'zapret'], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        subprocess.run(['taskkill', '/IM', 'winws.exe', '/F'], capture_output=True, timeout=5, creationflags=_NO_WINDOW)
        subprocess.run(['net', 'stop', 'WinDivert'], capture_output=True, timeout=5, creationflags=_NO_WINDOW)
        subprocess.run(['sc', 'delete', 'WinDivert'], capture_output=True, timeout=5, creationflags=_NO_WINDOW)
        return jsonify({'success': True, 'message': 'Service removed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings')
def api_settings():
    if not is_zapret_installed():
        return jsonify({'installed': False, 'font_size': _config.get('font_size', 14), 'zapret_dir': ZAPRET_DIR})
    return jsonify({
        'installed': True,
        'game_filter': get_game_filter(),
        'ipset_status': get_ipset_status(),
        'update_status': get_update_status(),
        'font_size': _config.get('font_size', 14),
        'zapret_dir': ZAPRET_DIR,
        'version': get_local_version(),
    })


@app.route('/api/settings/game', methods=['POST'])
def api_settings_game():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    mode = data.get('mode', 'disabled')
    if mode not in ('disabled', 'all', 'tcp', 'udp'):
        return jsonify({'error': 'Invalid mode'}), 400
    try:
        os.makedirs(UTILS_DIR, exist_ok=True)
        if mode == 'disabled':
            if os.path.exists(GAME_FLAG_FILE):
                os.remove(GAME_FLAG_FILE)
        else:
            with open(GAME_FLAG_FILE, 'w') as f:
                f.write(mode)
        return jsonify({'success': True, 'game_filter': get_game_filter()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/ipset', methods=['POST'])
def api_settings_ipset():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    mode = data.get('mode', 'loaded')
    if mode not in ('none', 'any', 'loaded'):
        return jsonify({'error': 'Invalid mode'}), 400
    list_file = os.path.join(LISTS_DIR, 'ipset-all.txt')
    backup_file = list_file + '.backup'
    try:
        current = get_ipset_status()
        if mode == 'none':
            if current == 'loaded':
                if os.path.exists(list_file):
                    if os.path.exists(backup_file):
                        os.remove(backup_file)
                    os.rename(list_file, backup_file)
            with open(list_file, 'w', encoding='utf-8') as f:
                f.write('203.0.113.113/32\n')
        elif mode == 'any':
            if current == 'loaded' and not os.path.exists(backup_file):
                shutil.copy2(list_file, backup_file)
            with open(list_file, 'w', encoding='utf-8') as f:
                f.write('')
        elif mode == 'loaded':
            if os.path.exists(backup_file):
                if os.path.exists(list_file):
                    os.remove(list_file)
                os.rename(backup_file, list_file)
        return jsonify({'success': True, 'ipset_status': get_ipset_status()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/update', methods=['POST'])
def api_settings_update():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    enabled = data.get('enabled', False)
    try:
        os.makedirs(UTILS_DIR, exist_ok=True)
        if enabled:
            with open(UPDATE_FLAG_FILE, 'w') as f:
                f.write('ENABLED')
        else:
            if os.path.exists(UPDATE_FLAG_FILE):
                os.remove(UPDATE_FLAG_FILE)
        return jsonify({'success': True, 'update_status': get_update_status()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/settings/font-size', methods=['POST'])
def api_settings_font_size():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    data = request.get_json() or {}
    size = data.get('size', 14)
    try:
        size = int(size)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid size'}), 400
    if size < 10 or size > 24:
        return jsonify({'error': 'Size must be 10-24'}), 400
    global _config
    _config['font_size'] = size
    save_config(_config)
    return jsonify({'success': True, 'font_size': size})


@app.route('/api/lists/<name>')
def api_list_read(name):
    if name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 404
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[name])
    try:
        if not os.path.exists(filepath):
            return jsonify({'content': '', 'exists': False})
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content, 'exists': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lists/<name>', methods=['POST'])
def api_list_write(name):
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 404
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    content = data.get('content', '')
    if len(content) > 10 * 1024 * 1024:
        return jsonify({'error': 'Content too large (max 10 MB)'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[name])
    lock = get_file_lock(filepath)
    with lock:
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/lists/<name>/add', methods=['POST'])
def api_list_add(name):
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 404
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    entry = data.get('entry', '').strip()
    if not entry:
        return jsonify({'error': 'Empty entry'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[name])
    lock = get_file_lock(filepath)
    with lock:
        try:
            existing = ''
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing = f.read()
            lines = [l.strip() for l in existing.splitlines() if l.strip()]
            if entry in lines:
                return jsonify({'error': 'Entry already exists', 'duplicate': True}), 409
            lines.append(entry)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/lists/<name>/remove', methods=['POST'])
def api_list_remove(name):
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 404
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    entry = data.get('entry', '').strip()
    if not entry:
        return jsonify({'error': 'Empty entry'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[name])
    lock = get_file_lock(filepath)
    with lock:
        try:
            if not os.path.exists(filepath):
                return jsonify({'error': 'File not found'}), 404
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            new_lines = [l for l in lines if l != entry]
            if len(new_lines) == len(lines):
                return jsonify({'error': 'Entry not found'}), 404
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines) + '\n' if new_lines else '')
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/diagnostics')
def api_diagnostics():
    def generate():
        yield '--- ZAPRET DIAGNOSTICS ---\n'
        yield 'Time: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\n\n'
        try:
            result = subprocess.run(['sc', 'query', 'BFE'], capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
            if 'RUNNING' in result.stdout:
                yield '[OK] Base Filtering Engine is running\n'
            else:
                yield '[FAIL] Base Filtering Engine is not running (required)\n'
        except Exception:
            yield '[FAIL] Could not check BFE service\n'
        yield '\n'
        proxy_enabled = False
        try:
            result = subprocess.run(
                ['reg', 'query', r'HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings', '/v', 'ProxyEnable'],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if '0x1' in result.stdout:
                proxy_enabled = True
        except Exception:
            pass
        if proxy_enabled:
            yield '[WARN] System proxy is enabled\n'
        else:
            yield '[OK] System proxy check passed\n'
        yield '\n'
        try:
            result = subprocess.run(
                ['netsh', 'interface', 'tcp', 'show', 'global'],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if 'enabled' in result.stdout.lower() and 'timestamps' in result.stdout.lower():
                yield '[OK] TCP timestamps enabled\n'
            else:
                yield '[WARN] TCP timestamps disabled - enable manually: netsh interface tcp set global timestamps=enabled\n'
        except Exception:
            yield '[WARN] Could not check TCP timestamps\n'
        yield '\n'
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq AdguardSvc.exe'],
                capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW
            )
            if 'adguardsvc.exe' in result.stdout.lower():
                yield '[FAIL] Adguard detected - conflicts with zapret\n'
            else:
                yield '[OK] Adguard check passed\n'
        except Exception:
            yield '[WARN] Could not check Adguard\n'
        yield '\n'
        for svc_name, label in [('Killer', 'Killer service'), ('SmartByte', 'SmartByte service'),
                                 ('Intel Connectivity Network Service', 'Intel Connectivity'),
                                 ('TracSrvWrapper', 'Check Point'), ('EPWD', 'Check Point')]:
            try:
                result = subprocess.run(['sc', 'query', svc_name], capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
                if result.returncode == 0:
                    yield '[FAIL] ' + label + ' found - conflicts with zapret\n'
                else:
                    yield '[OK] ' + label + ' check passed\n'
            except Exception:
                yield '[WARN] Could not check ' + label + '\n'
        yield '\n'
        sys_file = os.path.join(BIN_DIR, 'WinDivert64.sys')
        if os.path.exists(sys_file):
            yield '[OK] WinDivert64.sys found\n'
        else:
            yield '[FAIL] WinDivert64.sys not found\n'
        yield '\n'
        winws_running = is_winws_running()
        try:
            result = subprocess.run(['sc', 'query', 'WinDivert'], capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
            wd_active = 'RUNNING' in result.stdout or 'STOP_PENDING' in result.stdout
            if not winws_running and wd_active:
                yield '[WARN] WinDivert service active but winws not running - run "net stop WinDivert && sc delete WinDivert" to fix\n'
            elif wd_active:
                yield '[OK] WinDivert running with winws\n'
            else:
                yield '[OK] WinDivert not running (clean state)\n'
        except Exception:
            yield '[WARN] Could not check WinDivert\n'
        yield '\n'
        found_conflicts = []
        for svc in ['GoodbyeDPI', 'discordfix_zapret', 'winws1', 'winws2']:
            try:
                result = subprocess.run(['sc', 'query', svc], capture_output=True, text=True, timeout=5, creationflags=_NO_WINDOW)
                if result.returncode == 0:
                    found_conflicts.append(svc)
            except Exception:
                pass
        if found_conflicts:
            yield '[FAIL] Conflicting bypass services: ' + ', '.join(found_conflicts) + '\n'
        else:
            yield '[OK] No conflicting bypass services found\n'
        yield '\n--- DIAGNOSTICS COMPLETE ---\n'
    return Response(generate(), mimetype='text/plain', headers={'Cache-Control': 'no-cache'})


@app.route('/api/test-results')
def api_test_results():
    if not os.path.exists(RESULTS_DIR):
        return jsonify([])
    files = glob.glob(os.path.join(RESULTS_DIR, 'test_results_*.txt'))
    files.sort(reverse=True)
    results = []
    for f in files:
        name = os.path.basename(f)
        stat = os.stat(f)
        results.append({
            'name': name,
            'size': stat.st_size,
            'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
        })
    return jsonify(results)


@app.route('/api/test-results/<name>')
def api_test_result_content(name):
    filepath = os.path.join(RESULTS_DIR, name)
    if not os.path.exists(filepath) or '..' in name or '/' in name or '\\' in name:
        return jsonify({'error': 'Not found'}), 404
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'content': content})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tests/run', methods=['POST'])
def api_tests_run():
    csrf_err = check_csrf()
    if csrf_err:
        return csrf_err
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    test_script = os.path.join(UTILS_DIR, 'test zapret.ps1')
    if not os.path.exists(test_script):
        return jsonify({'error': 'Test script not found'}), 404
    try:
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(
            None, 'runas',
            'powershell.exe',
            f'-NoProfile -ExecutionPolicy Bypass -File "{test_script}"',
            ZAPRET_DIR,
            1
        )
        return jsonify({'success': True, 'message': 'Tests launched in PowerShell window'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/extension/status')
def api_extension_status():
    return jsonify({
        'installed': is_zapret_installed(),
        'running': is_winws_running() if is_zapret_installed() else False,
    })


@app.route('/api/extension/add', methods=['POST'])
def api_extension_add():
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    list_name = data.get('list', 'list-general-user')
    if not domain:
        return jsonify({'error': 'Empty domain'}), 400
    if list_name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[list_name])
    lock = get_file_lock(filepath)
    with lock:
        try:
            existing = ''
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing = f.read()
            lines = [l.strip() for l in existing.splitlines() if l.strip()]
            if domain in lines:
                return jsonify({'success': True, 'duplicate': True, 'message': domain + ' already in list'})
            lines.append(domain)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines) + '\n')
            return jsonify({'success': True, 'duplicate': False, 'message': domain + ' added'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/api/extension/remove', methods=['POST'])
def api_extension_remove():
    if not is_zapret_installed():
        return jsonify({'error': 'Zapret not installed'}), 400
    data = request.get_json() or {}
    domain = data.get('domain', '').strip()
    list_name = data.get('list', 'list-general-user')
    if not domain:
        return jsonify({'error': 'Empty domain'}), 400
    if list_name not in ALLOWED_LISTS:
        return jsonify({'error': 'Unknown list'}), 400
    filepath = os.path.join(LISTS_DIR, ALLOWED_LISTS[list_name])
    lock = get_file_lock(filepath)
    with lock:
        try:
            if not os.path.exists(filepath):
                return jsonify({'error': 'File not found'}), 404
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            new_lines = [l for l in lines if l != domain]
            if len(new_lines) == len(lines):
                return jsonify({'error': 'Domain not found'}), 404
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines) + '\n' if new_lines else '')
            return jsonify({'success': True, 'message': domain + ' removed'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import webview
    print('Zapret directory: ' + ZAPRET_DIR)
    print('Starting Zapret GUI...')
    server_thread = threading.Thread(target=lambda: app.run(host='127.0.0.1', port=8080, debug=False, threaded=True), daemon=True)
    server_thread.start()
    time.sleep(1)
    window = webview.create_window(
        'Zapret GUI',
        'http://127.0.0.1:8080',
        width=1100,
        height=700,
        min_size=(800, 500),
        text_select=True,
    )
    webview.start(gui='edgechromium', debug=False)
