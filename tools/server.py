import http.server
import json
import os
import shutil
import time

PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(DIRECTORY, 'location.csv')
EDGES_PATH = os.path.join(DIRECTORY, 'edges.json')
PHOTOS_DIR = os.path.join(DIRECTORY, 'photos_360')
BACKUP_DIR = os.path.join(DIRECTORY, '.backups')
MAX_BACKUPS_PER_FILE = 100


def backup(path):
    """Copy the current on-disk file into .backups/ before it gets overwritten."""
    if not os.path.exists(path):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = os.path.basename(path)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    dest = os.path.join(BACKUP_DIR, f'{name}.{stamp}.bak')
    if os.path.exists(dest):
        dest = os.path.join(BACKUP_DIR, f'{name}.{stamp}.{time.time_ns()}.bak')
    shutil.copy2(path, dest)
    prune(name)


def prune(name):
    backups = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.startswith(name + '.')),
        key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)),
    )
    for old in backups[:-MAX_BACKUPS_PER_FILE]:
        os.remove(os.path.join(BACKUP_DIR, old))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_POST(self):
        if self.path == '/save':
            self._save(CSV_PATH)
        elif self.path == '/save-edges':
            self._save(EDGES_PATH)
        elif self.path == '/rename':
            self._rename()
        else:
            self.send_response(404)
            self.end_headers()

    def _save(self, path):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        backup(path)
        with open(path, 'wb') as f:
            f.write(body)
        self.send_response(204)
        self.end_headers()

    def _rename(self):
        """Cascades a node rename (triggered from map_editor.html) into the
        two other places a node name is the key: its 360 photo filename and
        any edges.json entries referencing it by name. location.csv itself
        is NOT touched here - the client already holds the renamed point in
        memory and persists it via the normal /save call right after this."""
        length = int(self.headers.get('Content-Length', 0))
        try:
            data = json.loads(self.rfile.read(length))
            old_name, new_name = data['oldName'], data['newName']
        except (ValueError, KeyError):
            self.send_response(400)
            self.end_headers()
            return

        photo_renamed = False
        old_photo = os.path.join(PHOTOS_DIR, f'{old_name}.jpg')
        new_photo = os.path.join(PHOTOS_DIR, f'{new_name}.jpg')
        if os.path.exists(old_photo) and not os.path.exists(new_photo):
            os.rename(old_photo, new_photo)
            photo_renamed = True

        if os.path.exists(EDGES_PATH):
            with open(EDGES_PATH, encoding='utf-8') as f:
                edges = json.load(f)
            changed = False
            for e in edges:
                if e.get('from') == old_name:
                    e['from'] = new_name
                    changed = True
                if e.get('to') == old_name:
                    e['to'] = new_name
                    changed = True
            if changed:
                backup(EDGES_PATH)
                with open(EDGES_PATH, 'w', encoding='utf-8') as f:
                    json.dump(edges, f, ensure_ascii=False, indent=2)

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'ok': True, 'photoRenamed': photo_renamed}).encode('utf-8'))

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


if __name__ == '__main__':
    with http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler) as httpd:
        print(f"Serving at http://127.0.0.1:{PORT}/map_editor.html")
        print(f"Backups of every save go to {BACKUP_DIR}")
        httpd.serve_forever()
