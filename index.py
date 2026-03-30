import json
from pathlib import Path
import time
import sys
# sys.path.append(str(Path(__file__).parent.resolve()))

from colors import bcolors 
from git_objects import Blob, Tree
from utils import get_file_from_commit, get_parent_hash, read_from_blob


class Index:
    def __init__(self):
        self.repo_path = Path.cwd().resolve()
        self.index_file_path = self.repo_path / '.git' / 'index.json'

    def index_add(self,file_path):
        with open(self.index_file_path) as f:
            d = json.load(f)
        
        file = Path(file_path).resolve()
        rel_key = file.relative_to(self.repo_path).as_posix()

        index_path = rel_key
        if file.exists() == False:
                del d[index_path]
        
        else:
            file_stat = file.stat() 
            blob = Blob(file)
            file_hash = blob.save()

            d[rel_key] = {'hash':file_hash,
                                    'ct_time':time.ctime(file_stat.st_ctime),
                                    'mt_time':time.ctime(file_stat.st_mtime),
                                    'size':file_stat.st_size,
                                    'mode': "100644",
                                    'file_name':file.name}

        
        with open(self.index_file_path,'w') as f:
            json.dump(d,f)

    def status(self):
        print(bcolors.BOLD + "changes to be commited" + bcolors.ENDC)
        self.status_index_and_commit()
        print("\n")
        print(bcolors.BOLD + "changes to be stages" + bcolors.ENDC)
        with open(self.index_file_path) as f:
            d = json.load(f)
        for file in self.repo_path.rglob("*") :
            if not any(part.startswith('.') for part in file.parts):
                if file.is_file():
                    # new file
                    file = Path(file).resolve()
                    rel_key = file.relative_to(self.repo_path).as_posix()
                    if rel_key not in d:
                        print(bcolors.BLUE + "untracked files: ", file.relative_to(self.repo_path).as_posix() + 
                                                                                                        bcolors.BLUE)
                    # modified file
                    else:
                        index_file = d[rel_key]
                        file_stat = file.stat()
                        if index_file['mt_time'] != time.ctime(file_stat.st_mtime):
                            if index_file['hash'] != Blob.read_and_hash_blob(file):
                                print(bcolors.GREEN + "modified file: ",file.relative_to(self.repo_path).as_posix() + 
                                                                                                            bcolors.ENDC)
                        del d[rel_key]
            
        # deleted files
        if len(d)>0:
            for key in d.keys():
                print(bcolors.RED + "deleted files: ", key + bcolors.ENDC)

    def status_index_and_commit(self):
        commit_hash = get_parent_hash()
        root_tree = read_from_blob(commit_hash)[1].split('\n')[0].split(" ")[1]
        commit_index = Tree.construct_tree_from_root_tree(root_tree)
        
        with open(self.index_file_path,'r') as file:
            index = json.load(file)

        for key,value in index.items():
            if key in commit_index:
                if value['hash'] != commit_index[key]['hash']:
                    print(bcolors.GREEN + f"modified file: {key}" + bcolors.ENDC)
                del commit_index[key]
            elif key not in commit_index:
                print(bcolors.GREEN + f"added file: {key}" + bcolors.ENDC)

        for key in commit_index.keys():
            print(bcolors.RED + f"deleted file: {key}" + bcolors.ENDC)

    @staticmethod                    
    def construct_tree_from_json(index_file_path):
        tree = {}
        with open(index_file_path,'r') as file:
            content = file.read()
        
        content = json.loads(content)
        for key,value in content.items():
            path = key.split('/')
            
            current_level = tree
            for folder in path[:-1]:
                if folder not in current_level:
                    current_level[folder] = {}
                current_level = current_level[folder]
            
            file_name = path[-1]
            current_level[file_name] = [
                value["hash"],
                value["mode"],
                value["file_name"]
            ]
        return tree

    def add_all(self):
        index = {}
        for file in self.repo_path.rglob("*"):
            if not any(part.startswith('.') for part in file.parts):
                if file.is_file():
                    file = file.resolve()
                    rel_key = file.relative_to(self.repo_path).as_posix()
                    blob = Blob(file)
                    file_hash = blob.save()
                    stats = file.stat()
                    index[rel_key] = {'hash':file_hash,
                                        'ct_time':time.ctime(stats.st_ctime),
                                        'mt_time':time.ctime(stats.st_mtime),
                                        'size':stats.st_size,
                                        'mode': "100644",
                                        'file_name':file.name}

        with open(self.index_file_path,'w') as file:
            json.dump(index, file)


    def unstage_file(self,file):
        commit_hash = get_parent_hash()
        root_tree = read_from_blob(commit_hash)[1].split('\n')[0].split(" ")[1]
        file_content = get_file_from_commit(root_tree,file)
        with open(self.index_file_path,'r') as f:
            d = json.load(f)

        if file_content != None:
            rel_key,file_hash = file_content
            file = Path(file)
            file_stat = file.stat()
            d[rel_key]['hash'] = file_hash
            d[rel_key]['mt_time'] = time.ctime(file_stat.st_mtime)
        else:
            del d[file]
            
        with open(self.index_file_path,'w') as f:
            json.dump(d,f)
        
        print(f"{file} has been removed form staging")
            



# index = Index()
# index.unstage_file()