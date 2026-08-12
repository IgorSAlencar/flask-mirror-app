from flask import Flask, render_template, request, redirect, send_from_directory, send_file, abort
import os, json, io, shutil, urllib.error, urllib.request
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Diretório gravável em Serverless
BASE_DIR = os.environ.get('DATA_DIR', '/tmp/data')
os.makedirs(BASE_DIR, exist_ok=True)

# Configurações do mirror
UPSTREAM_REPO = os.environ.get(
    'UPSTREAM_REPO',
    'https://github.com/IgorSAlencar/mapa-hierarquia-visualiza.git'
)
UPSTREAM_NAME = os.environ.get('UPSTREAM_NAME', 'mapa-hierarquia-visualiza')
UPSTREAM_REPO_RE = os.environ.get(
    'UPSTREAM_REPO_RE',
    'https://github.com/IgorSAlencar/Reestruturacao_Equipe.git'
)
UPSTREAM_NAME_RE = os.environ.get('UPSTREAM_NAME_RE', 'Reestruturacao_Equipe')

def _github_repo_base(repo_url):
    return repo_url.rstrip('/').removesuffix('.git')

def _free_tmp_space():
    """Libera espaço residual em /tmp (limite baixo na Vercel)."""
    if not os.path.exists(BASE_DIR):
        return
    for name in os.listdir(BASE_DIR):
        path = os.path.join(BASE_DIR, name)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError as e:
            app.logger.warning(f"Falha ao limpar {path}: {e}")

def clone_and_zip(repo_url, repo_name):
    """Baixa o ZIP do GitHub (archive) sem clonar o histórico .git em disco."""
    _free_tmp_space()
    base = _github_repo_base(repo_url)
    last_error = None

    for branch in ('main', 'master'):
        archive_url = f"{base}/archive/refs/heads/{branch}.zip"
        try:
            req = urllib.request.Request(
                archive_url,
                headers={'User-Agent': 'flask-mirror-app'}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            mem_zip = io.BytesIO(data)
            mem_zip.seek(0)
            return send_file(
                mem_zip,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f"{repo_name}.zip"
            )
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 404:
                continue
            app.logger.error(f"GitHub archive error: {e}")
            abort(500, f"Download error: {e}")
        except Exception as e:
            last_error = e
            app.logger.error(f"GitHub archive error: {e}")
            abort(500, f"Download error: {e}")

    abort(500, f"Download error: branch not found ({last_error})")

def save_commit(repo_name, files, message):
    repo_path = os.path.join(BASE_DIR, repo_name)
    os.makedirs(repo_path, exist_ok=True)
    version = datetime.now().strftime('v%Y%m%d%H%M%S')
    version_path = os.path.join(repo_path, version)
    os.makedirs(version_path)
    for f in files:
        filename = secure_filename(f.filename)
        f.save(os.path.join(version_path, filename))
    commit_log = os.path.join(repo_path, 'commits.json')
    commits = []
    if os.path.exists(commit_log):
        with open(commit_log) as cf:
            commits = json.load(cf)
    commits.append({
        'version': version,
        'timestamp': datetime.now().isoformat(),
        'message': message,
        'files': [secure_filename(f.filename) for f in files]
    })
    with open(commit_log, 'w') as cf:
        json.dump(commits, cf, indent=2)
    return version

@app.route('/')
def index():
    repos = os.listdir(BASE_DIR)
    return render_template('index.html', repos=repos)

@app.route('/repo/<name>')
def view_repo(name):
    repo_path = os.path.join(BASE_DIR, name)
    commits_file = os.path.join(repo_path, 'commits.json')
    if not os.path.exists(commits_file):
        return "Repositório vazio ou inexistente.", 404
    with open(commits_file) as cf:
        commits = json.load(cf)
    return render_template('repo.html', name=name, commits=commits)

@app.route('/upload/<repo>', methods=['GET', 'POST'])
def upload(repo):
    if request.method == 'POST':
        files = request.files.getlist('files')
        message = request.form.get('message', 'Sem mensagem')
        save_commit(repo, files, message)
        return redirect(f'/repo/{repo}')
    return """
    <form method='post' enctype='multipart/form-data'>
        Mensagem: <input type='text' name='message'><br>
        Arquivos: <input type='file' name='files' multiple><br>
        <input type='submit' value='Enviar'>
    </form>
    """

@app.route('/download/<repo>/<version>/<filename>')
def download_file(repo, version, filename):
    path = os.path.join(BASE_DIR, repo, version)
    return send_from_directory(path, filename, as_attachment=True)

@app.route('/dwn')
def mirror():
    return clone_and_zip(UPSTREAM_REPO, UPSTREAM_NAME)

@app.route('/dwn_re')
def mirror_re():
    return clone_and_zip(UPSTREAM_REPO_RE, UPSTREAM_NAME_RE)

if __name__ == '__main__':
    app.run(debug=True)
