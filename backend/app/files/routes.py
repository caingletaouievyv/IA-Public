# IA/backend/app/files/routes.py
"""GET /: return folder tree from cwd; exclude common build/cache dirs and binary ext."""

import os
from flask import Blueprint, jsonify
from app.common.auth import require_auth

bp = Blueprint("files", __name__)

@bp.route("/", methods=["GET"])
def list_files():
    user_id, auth_err = require_auth()
    if auth_err:
        return auth_err
    return jsonify(build_file_tree(os.getcwd()))

def build_file_tree(path):
    """Recurse path; build {name, type, path, children}; skip exclude_dirs and exclude_ext."""
    exclude_dirs = {"bin", "obj", ".vs", "node_modules", "Migrations", "wwwroot", "__pycache__"}
    exclude_ext = {".dll", ".pdb", ".exe", ".log"}
    tree = {"name": os.path.basename(path), "type": "folder", "path": os.path.relpath(path), "children": []}
    try:
        for entry in sorted(os.listdir(path)):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path) and entry not in exclude_dirs:
                tree["children"].append(build_file_tree(full_path))
            elif os.path.isfile(full_path) and os.path.splitext(entry)[1].lower() not in exclude_ext:
                tree["children"].append({"name": entry, "type": "file", "path": os.path.relpath(full_path)})
    except PermissionError:
        pass
    return tree
