import hashlib
import json
from pathlib import Path
import time
import zlib
from utils import delete_file_and_parent_folders, read_from_blob, read_objects, write_to_file
import sys
sys.path.append(str(Path(__file__).parent.resolve()))

class Git_objects:
    
    repo_path = Path.cwd().resolve()
    index_file_path = repo_path / '.gitty' / 'index.json'
    
    def __init__(self,object_type,data):
        self.repo_path = Path.cwd()
        self.BLOB_PATH = self.repo_path / '.gitty'/ 'objects'
        self.object_type = object_type
        self.data = data if isinstance(data,bytes) else data.encode()
        self.header = f"{self.object_type} {len(self.data)}".encode() + b"\00"
        self.full_data = self.header + self.data

    def save(self):
        hash = hashlib.sha1(self.full_data)
        compressed = self.handle_compress(self.full_data)
        self.handle_save(hash,compressed)

        return hash.hexdigest()

    def handle_save(self,hash,compressed_content):
        hash = hash.hexdigest()
        folder_name,file_name = hash[:2],hash[2:]
        blob_folder_path=self.BLOB_PATH/folder_name
        blob_folder_path.mkdir(exist_ok=True)
        with (blob_folder_path/file_name ).open('wb') as file:
                file.write(compressed_content)
    
    def handle_compress(self,file):
        compressed = zlib.compress(file)
        return compressed

class Blob(Git_objects):
    def __init__(self,file_path):
        self.file_path = file_path
        with (self.file_path).open('r') as file:
                content = file.read()
        super().__init__("Blob",content)
        
    @staticmethod
    def read_and_hash_blob(file_path):
        with (file_path).open('r') as file:
            content = file.read().encode()

        header = f"Blob {len(content)}".encode() + b'\x00'
        full_data = header + content
        hash = hashlib.sha1(full_data)
        
        return hash.hexdigest()

    def read_file_content(self):
        with (self.file_path).open('r') as file:
            content = file.read()
        return content

class Tree(Git_objects):
    def __init__(self,dict):
        self.tree_dict = dict
        content = json.dumps(self.tree_dict, sort_keys=True).encode()
        super().__init__("Tree",content)

    @staticmethod
    def construct_from_unflattened(unflattened_tree):
        root_tree_content = {}
        for file in unflattened_tree.keys():
            if type(unflattened_tree[file]) == dict:
                tree_hash = Tree.construct_from_unflattened(unflattened_tree[file])
                root_tree_content[tree_hash] = ('Tree',file)
            else:
                root_tree_content[unflattened_tree[file][0]] = ('Blob',unflattened_tree[file][2])
        tree_obj = Tree(root_tree_content)
        hash_hex = tree_obj.save()
        return hash_hex
    
    @staticmethod
    def construct_index_from_root_tree(root_tree,path_list=[]):
        commit_index = {}
        tree_header,tree_content = read_from_blob(root_tree)
        tree_content = json.loads(tree_content)
        for key,value in tree_content.items():
            if value[0] == "Tree":
                path_list.append(value[1])
                index = Tree.construct_index_from_root_tree(key,path_list)
                commit_index.update(index)
                path_list.pop()
            else:
                if path_list:
                    file_path = Tree.repo_path / f'{'/'.join(path_list)}/{value[1]}'
                else:
                    file_path = Tree.repo_path / value[1]
                rel_path = file_path.relative_to(Tree.repo_path).as_posix()
                commit_index[rel_path] =  {'hash':key}
        return commit_index
    

class Commit(Git_objects):
    def __init__(self,tree_hash,parent_hash,message,author):
        lines = [f"tree {tree_hash}"]
        if parent_hash and parent_hash != 'None':
            lines.append(f"parent {parent_hash}")
        lines.append(f"author {author}")
        lines.append(f"time {time.ctime(time.time())}")
        lines.append("") 
        lines.append(message)

        formatted_body = "\n".join(lines)

        super().__init__("Commit",formatted_body)       

    @staticmethod
    def read_commit(commit_hash):
        commit_content = read_from_blob(commit_hash)[1].split('\n')
        commit_content_dict = {}
        for i in commit_content:
            if i == "":
                continue
            content = i.split(" ")
            if content[0] == "parent":
                commit_content_dict['parent'] = content[1].split(",")
            elif content[0] == "author":
                commit_content_dict['author'] = content[1]
            elif content[0] == "time":
                commit_content_dict['time'] = ' '.join(content[1:])
            elif content[0] == "tree":
                commit_content_dict['tree'] = content[1]
            else:
                commit_content_dict['message'] = i
        return commit_content_dict

    # overriding the current workspace with the checking out workspace (can also be used for reset commands)
    @staticmethod
    def commit_content(commit_hash):
        # 1. Load the current index (what is on disk now)
        with open(Commit.index_file_path, 'r') as file:
            old_index = json.loads(file.read())

        # 2. Get the new tree hash from the commit blob
        content_blob = read_from_blob(commit_hash)
        # Adjust this index [1] if your read_from_blob returns (header, body)
        new_tree_hash = content_blob[1].split('\n')[0].split(' ')[1]

        # 3. Build the NEW index and write files to disk
        # We pass an empty dict for recreated_index
        recreated_index = {}
        Commit.over_ride_contents(new_tree_hash, recreated_index, [])

        # 4. DELETE ONLY what is not in the new index
        # We iterate over a copy of keys to be safe
        for old_path in list(old_index.keys()):
            if old_path not in recreated_index:
                file_path = Commit.repo_path / old_path
                delete_file_and_parent_folders(file_path)

        # 5. Save the new index
        with open(Commit.index_file_path, 'w') as file:
            json.dump(recreated_index, file, indent=4)
            
    @staticmethod
    def over_ride_contents(root_tree, recreated_index, path_list):
        tree_header, tree_content = read_from_blob(root_tree)
        tree_data = json.loads(tree_content)
        
        for obj_hash, info in tree_data.items():
            obj_type, obj_name = info[0], info[1]
            
            # Build path carefully
            current_rel_path = "/".join(path_list + [obj_name])
            
            if obj_type == "Tree":
                # Recurse
                Commit.over_ride_contents(obj_hash, recreated_index, path_list + [obj_name])
            else:
                # File logic
                full_path = Commit.repo_path / current_rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                h, contents = read_from_blob(obj_hash)
                write_to_file(full_path, contents)
                
                stat = full_path.stat()
                recreated_index[current_rel_path] = {
                    'hash': obj_hash,
                    'ct_time': time.ctime(stat.st_ctime),
                    'mt_time': time.ctime(stat.st_mtime),
                    'size': h.split(" ")[1],
                    'mode': "100644",
                    'file_name': obj_name
                }