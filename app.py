from flask import Flask, render_template, request, redirect, send_from_directory, send_file, abort
import os, json, io, zipfile, shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from dulwich import porcelain

app = Flask(__name__)

# Diretório gravável em Serverless
BASE_DIR = os.environ.get('DATA_DIR', '/tmp/data')
os.makedirs(BASE_DIR, exist_ok=True)

# Configurações do mirror
UPSTREAM_REPO = os.environ.get(
    'UPSTREAM_REPO',
    'https://github.com/IgorSAlencar/gestao-comercial.git'
)
UPSTREAM_NAME = os.environ.get('UPSTREAM_NAME', 'gestao-comercial')

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

@app.route('/mirror')
def mirror():
    local_path = os.path.join(BASE_DIR, UPSTREAM_NAME)
    # limpa execuções anteriores
    if os.path.exists(local_path):
        shutil.rmtree(local_path)
    try:
        porcelain.clone(UPSTREAM_REPO, local_path)
    except Exception as e:
        app.logger.error(f"Dulwich clone error: {e}")
        abort(500, f"Clone error: {e}")

    # empacota num ZIP
    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(local_path):
            for file in files:
                full = os.path.join(root, file)
                arc = os.path.relpath(full, local_path)
                zf.write(full, arc)
    mem_zip.seek(0)
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{UPSTREAM_NAME}.zip"
    )

if __name__ == '__main__':
    app.run(debug=True)
