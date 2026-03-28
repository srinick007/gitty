import hashlib
import json
from pathlib import Path
import time
import zlib
from utils import read_from_blob, read_objects, write_to_file

class Git_objects:
    
    repo_path = Path.cwd().resolve()
    index_file_path = repo_path / '.git' / 'index.json'
    
    def __init__(self,object_type,data):
        self.repo_path = Path.cwd()
        self.BLOB_PATH = self.repo_path / '.git'/ 'objects'
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
    def construct_tree_from_root_tree(root_tree,path_list=[]):
        commit_index = {}
        tree_header,tree_content = read_from_blob(root_tree)
        tree_content = json.loads(tree_content)
        for key,value in tree_content.items():
            if value[0] == "Tree":
                path_list.append(value[1])
                index = Tree.construct_tree_from_root_tree(key,path_list)
                commit_index.update(index)
                path_list.pop()
            else:
                if path_list:
                    file_path = Tree.repo_path / f'{'/'.join(path_list)}/{value[1]}'
                else:
                    file_path = Tree.repo_path / value[1]
                rel_path = file_path.relative_to(Tree.repo_path).as_posix()
                commit_index[rel_path] =  read_from_blob(key)[1].split("\n")
        return commit_index
    

class Commit(Git_objects):
    def __init__(self,tree_hash,parent_hash,message,author):
        lines = [f"tree {tree_hash}"]
        if parent_hash and parent_hash != 'None':
            lines.append(f"parent {parent_hash}")
        lines.append(f"author {author}")
        lines.append("") 
        lines.append(message)

        formatted_body = "\n".join(lines)

        super().__init__("Commit",formatted_body)       

    @staticmethod
    def commit_content(commit_hash):
        with open(Commit.index_file_path,'r') as file:
            old_index = file.read()
        old_index = json.loads(old_index)

        content = read_from_blob(commit_hash)
        
        # getting new branch tree object from commit message
        content = content[1].split('\n')[0].split(' ')[1]
        recreated_index = Commit.over_ride_contents(content,old_index)

        # deleting the files that are not in checking out branch by comparing it with current branch
        for key in old_index.keys():
            file_path = Commit.repo_path / key
            file_path.unlink(missing_ok=False)
            parent_dir = file_path.parent
            result = True if (parent_dir.is_dir() and list(parent_dir.iterdir()) == []) else False
            if result:
                parent_dir.rmdir()

        # creates the new index
        with open(Commit.index_file_path,'w') as file:
            json.dump(recreated_index, file)
        

    @staticmethod
    def over_ride_contents(root_tree,old_index,path_list=[]):
        recreated_index = {}
        tree_header,tree_content = read_from_blob(root_tree)
        tree_content = json.loads(tree_content)
        # print(tree_content)
        
        # key is hash and value is a list that mentions the type of blob and file/folder name
        # over rides the content of the files by using the checking out branch tree object
        for key,value in tree_content.items():
            if value[0] == "Tree":
                path_list.append(value[1])
                index = Commit.over_ride_contents(key,old_index,path_list)
                recreated_index.update(index)
                path_list.pop()
            else:
                if path_list:
                    file_path = Commit.repo_path / f'{'/'.join(path_list)}/{value[1]}'
                else:
                    file_path = Commit.repo_path / value[1]
                file_header,file_contents = read_from_blob(key)
                file_size = file_header.split(" ")[1]
                
                # over writing existing files/ adding new files and creating the new branch index
                write_to_file(file_path,file_contents)
                file_stat = file_path.stat()
                rel_key = file_path.relative_to(Commit.repo_path).as_posix()
                recreated_index[rel_key] = {'hash':key,
                            'ct_time':time.ctime(file_stat.st_ctime),
                            'mt_time':time.ctime(file_stat.st_mtime),
                            'size':file_size,
                            'mode': "100644",
                            'file_name':value[1]}

                # if both branches have overlap files delete the key for comparison (on which files to delete 
                #                                                                    when changing to new branch)
                if rel_key in old_index:
                    del old_index[rel_key]

        return recreated_index
