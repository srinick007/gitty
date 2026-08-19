import json
from pathlib import Path

from gitty.git_objects import Commit
from gitty.utils import read_from_blob

def get_repo_path() -> Path:
    return Path.cwd().resolve()

def get_blob_path(repo_path: Path = None) -> Path:
    base = Path(repo_path) if repo_path else get_repo_path()
    return base / '.gitty' / 'objects'

def commit_full_walk(root_tree):
    commit_index = {}
    tree_header,tree_content = read_from_blob(root_tree)
    tree_content = json.loads(tree_content)
    for key,value in tree_content.items():
        if value[0] == "Tree":
            folder_name,file_name = key[:2],key[2:]
            file = open(get_blob_path() / folder_name / file_name, 'rb').read()
            commit_index[key] = {'type':'tree','content':file}
            index = commit_full_walk(key)
            commit_index.update(index)
        else:
            folder_name,file_name = key[:2],key[2:]
            file = open(get_blob_path() / folder_name / file_name, 'rb').read()
            commit_index[key] =  {'type':'blob','content':file}
    return commit_index

def commit_full_walk_just_hashes(root_tree):
    commit_index = {}
    tree_header,tree_content = read_from_blob(root_tree)
    tree_content = json.loads(tree_content)
    for key,value in tree_content.items():
        if value[0] == "Tree":
            commit_index[key] = {'type':'tree'}
            index = commit_full_walk_just_hashes(key)
            commit_index.update(index)
        else:
            commit_index[key] =  {'type':'blob'}
    return commit_index

def get_hashes(commit_hash):
    all_hashes = {}
    seen_commit = set()
    queue = [commit_hash]

    while queue:
        current_commit = queue.pop(0)
        if not current_commit or current_commit in seen_commit or current_commit == "None":
            continue
        
        seen_commit.add(current_commit)
        all_hashes[current_commit] = {'type': 'commit'}

        commit_content = Commit.read_commit(current_commit)
        
        # Collect root tree and all nested trees/blobs
        tree_hash = commit_content.get('tree')
        if tree_hash:
            all_hashes[tree_hash] = {'type': 'tree'}
            commit_tree = commit_full_walk_just_hashes(tree_hash)
            all_hashes.update(commit_tree)
            
        # Add parent commits to queue so full history is collected
        parents = commit_content.get('parent', [])
        for parent in parents:
            if parent and parent not in seen_commit:
                queue.append(parent)
    
    return all_hashes

def check_missing(missing: dict):
    requried = []
    for key in missing.keys():
        folder,file_name = key[:2],key[2:]
        blob_exist_locally = Path(get_blob_path() / folder/ file_name)
        if not blob_exist_locally.exists():
            requried.append(key)

    # print(requried)
    return requried

def ref_saver(repo_path,path,ref,ref_hash):
    remote_ref_dir = repo_path / '.gitty' / 'refs' / path
    remote_ref_dir.mkdir(parents=True, exist_ok=True)

    remote_ref_file = remote_ref_dir / ref
    # print(remote_ref_file)
    remote_ref_file.write_text(ref_hash.strip())
    return 
# print(read_from_blob('17c5390177551d25ca04ea600bd9200dd6c4ab6e'))
# print(commit_full_walk('1a1c099eaee07fce9734085b9232f70919434a05'))