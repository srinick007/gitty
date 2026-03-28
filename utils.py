import hashlib
import json
from pathlib import Path
import zlib

repo_path = Path.cwd().resolve()
BLOB_PATH = repo_path/ '.git'/'objects'


def get_parent_hash():
        head_path = repo_path / '.git' / 'HEAD'
        if not head_path.exists():
            return None
        
        content = head_path.read_text().strip()
        
        if content.startswith('ref:'):
            ref_path = repo_path / '.git' / content.split(' ')[1]
            if ref_path.exists():
                return ref_path.read_text().strip()
            return None
        
        return content

def dic_to_json(dic):
    serialized_dict = json.dumps(dic, sort_keys=True, ensure_ascii=True).encode()
    header = f"Tree {len(serialized_dict)}".encode() + b'\x00'
    full_data = header + serialized_dict
    return full_data

def handle_compress(file):
    compressed = zlib.compress(file)
    return compressed

def handle_save(hash,compressed_content):
    hash = hash.hexdigest()
    folder_name,file_name = hash[:2],hash[2:]
    blob_folder_path=BLOB_PATH/folder_name
    blob_folder_path.mkdir(exist_ok=True)
    with (blob_folder_path/file_name ).open('wb') as file:
            file.write(compressed_content)

def read_and_hash_file(file):
    with (file).open('r') as file:
        content = file.read().encode()

        header = f"Blob {len(content)}".encode() + b'\x00'
        full_data = header + content
        compressed = handle_compress(full_data)
        hash = hashlib.sha1(full_data)

    # handle_save(hash,compressed)
    
    return hash


def write_to_file(file_path,file_content):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(file_content)


def read_from_blob(blob):
    folder_name,file_name = blob[:2],blob[2:]
    with (BLOB_PATH/folder_name/file_name).open('rb') as file:
        content = file.read()
        decompressed =  zlib.decompress(content)
        content = decompressed.split(b'\x00')
        header,data = content[0].decode('utf-8'),content[1].decode('utf-8')
        return (header,data)

def read_objects(root_tree,path,level = 0,):
    commit_index = {}
    tree_header,tree_content = read_from_blob(root_tree)
    tree_content = json.loads(tree_content)
    # print(tree_content)
    # key is hash and value is a list that mentions the type pf blob and file/folder name
    for key,value in tree_content.items():
        if value[0] == "Tree":
            path.append(value[1])
            # print(" "*level,value[1],)
            index = read_objects(key,path,level+2)
            commit_index.update(index)
            path.pop()
        else:
            if path:
                file_path = repo_path / f'{'/'.join(path)}/{value[1]}'
            else:
                file_path = repo_path / value[1]
            rel_path = file_path.relative_to(repo_path).as_posix()
            commit_index[rel_path] =  read_from_blob(key)[1].split("\n")
            # print(" "*level, read_from_blob(key)[1],value[1],rel_path)
    return commit_index

def get_file_from_commit(root_tree,file,path_list=[]):
    tree_header,tree_content = read_from_blob(root_tree)
    tree_content = json.loads(tree_content)
    
    for key,value in tree_content.items():
        if value[0] == "Tree":
            path_list.append(value[1])
            blob_hash = get_file_from_commit(key,file,path_list)
            if blob_hash and len(blob_hash):
                return blob_hash
            path_list.pop()
        else:
            if path_list:
                file_path = repo_path / f'{'/'.join(path_list)}/{value[1]}'
            else:
                file_path = repo_path / value[1]
            rel_path = file_path.relative_to(repo_path).as_posix()
            if rel_path == file:
                    return (rel_path,key)
    # return (None,None)

# print(get_file_from_commit('2879cd3d6634318121fa580024232843dbb0226c','sub_folder1/sub1_folder.py'))

# print(read_from_blob('3431b553d5db55a536376ab075ed4198fcaab546')[1])
# print(read_objects('0452e49af5ce13210fca557e3afb5d27901a29b3',[]))
# print(read_from_blob('31be9cc7a8f7f6c6eb228d40979d7fdb0d96ef95'))