import json
from pathlib import Path
import time

from colors import bcolors 
from git_objects import Blob, Tree, Commit
from utils import get_current_branch, get_file_from_commit, get_current_head_hash, read_from_blob, temp_index_exist


class Index:
    def __init__(self):
        self.repo_path = Path.cwd().resolve()
        self.index_file_path = self.repo_path / '.gitty' / 'index.json'

    @staticmethod
    def check_conflict_in_file(blob,file_path):
        file_contents = blob.read_file_content()
        window_size = 12
        i = 0
        while i<len(file_contents):
            if file_contents[i:i+window_size] == "<<<<<<< HEAD":
                print(bcolors.RED)
                print(f"There is a conflict in the file {file_path}. Please resolve it to add the file to index")
                print(bcolors.ENDC)
                return True
            i+=1

        return False
    
    def index_add(self,file_path):
        # if temp index present
        is_merge = temp_index_exist()
        temp_index_path = self.repo_path / '.gitty' / 'temp_merge_index.json'

        file = Path(file_path).resolve()
        rel_key = file.relative_to(self.repo_path).as_posix()

        if is_merge:
            target_index = temp_index_path
            with open(target_index) as f:
                d = json.load(f)
            # if the file not in temp index ie. new file, add to regular index
            if rel_key not in d:
                target_index = self.index_file_path
                with open(target_index) as f:
                    d = json.load(f)
                is_merge = False
            else:
                target_index = temp_index_path
        else:
            target_index = self.index_file_path
            with open(target_index) as f:
                d = json.load(f)
            is_merge = False

        
        if file.exists() == False:
                if rel_key in d:
                    if temp_index_exist():
                        d[rel_key]['action'] = 'DELETE'
                        d[rel_key]['conflict_status'] = False
                    else:
                        del d[rel_key]
                else:
                    print(f"File {file_path} does not exist")
                    return
                
        else:
            file_stat = file.stat() 
            blob = Blob(file)
            # merge temp index
            if temp_index_exist():
                if Index.check_conflict_in_file(blob,file_path):
                    return 
                file_hash = blob.save()
                d[rel_key]['conflict_status'] = False
                d[rel_key]['resolved_hash'] = file_hash
                d[rel_key]['action'] = 'CREATE_FILE'
            # normal index
            else:
                file_hash = blob.save()

                d[rel_key] = {'hash':file_hash,
                                'ct_time':time.ctime(file_stat.st_ctime),
                                'mt_time':time.ctime(file_stat.st_mtime),
                                'size':file_stat.st_size,
                                'mode': "100644",
                                'file_name':file.name}

        
        with open(target_index,'w') as f:
            json.dump(d,f)


    def status_temp_merge(self):
        with open(self.repo_path / '.gitty'/ 'MERGE_MSG','r') as f:
            msg = f.read().strip()
            merging_branch = msg.split("'")[1]
        with open(self.repo_path / '.gitty' / 'temp_merge_index.json','r') as f:
            temp_merge_index = json.load(f)
        
        current_branch = get_current_branch()
        
        print(bcolors.BOLD)
        print(f"**On branch {current_branch}, currently merging {merging_branch}.**")
        conflicted_files = []
        ready_to_commit_files = []
        for key,value in temp_merge_index.items():
            if value['conflict_status'] == True:
                conflicted_files.append(key)
            else:
                ready_to_commit_files.append((key,value['action']))
        
        if conflicted_files:
            print(bcolors.RED)
            print("Fix these files manually")
            for file in conflicted_files:
                print(file)
            print(bcolors.ENDC)
        
        if ready_to_commit_files:
            print("Ready to be Commited")
            for file in ready_to_commit_files:
                color = bcolors.GREEN
                if file[1] == 'DELETE':
                    color = bcolors.RED

                print(color + file[0] + bcolors.ENDC )
        print("\n")

    def status(self):
        
        involved_in_merge = set()
        if temp_index_exist():
            self.status_temp_merge()
            with open(self.repo_path / '.gitty' / 'temp_merge_index.json', 'r') as f:
                temp_idx = json.load(f)
        
            involved_in_merge = set(temp_idx.keys())

        print(bcolors.BOLD + "changes to be commited" + bcolors.ENDC)
        self.status_index_and_commit(exclude = involved_in_merge)
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

                    # skip if the file is in merge index 
                    if rel_key in involved_in_merge:
                        if rel_key in d: 
                            del d[rel_key] # Remove so it doesn't show as deleted later
                        continue

                    if rel_key not in d and rel_key not in involved_in_merge:
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
                if key not in involved_in_merge:
                    print(bcolors.RED + "deleted files: ", key + bcolors.ENDC)

    def status_index_and_commit(self,exclude = None):
        if exclude is None:
            exclude = set()

        commit_hash = get_current_head_hash()
        if not commit_hash:
            return
        
        root_tree = Commit.read_commit(commit_hash)['tree']
        commit_index = Tree.construct_index_from_root_tree(root_tree)
        
        with open(self.index_file_path,'r') as file:
            index = json.load(file)

        for key,value in index.items():
            
            # skip if the file is in merge index 
            if key in exclude:
                if key in commit_index: del commit_index[key]
                continue

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
        if temp_index_exist():
            print(bcolors.RED + "functionality 'add .' does not work when mergeing is in progress use add <file> to add individual files" + bcolors.ENDC)
            return
        
        index = {}
        for file in self.repo_path.rglob("*"):
            if not any(part.startswith('.') for part in file.parts):
                if file.is_file():
                    file = file.resolve()
                    rel_key = file.relative_to(self.repo_path).as_posix()
                    blob = Blob(file)
                    if Index.check_conflict_in_file(blob,rel_key):
                        continue 
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
        commit_hash = get_current_head_hash()
        root_tree = Commit.read_commit(commit_hash)['tree']
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
            if file in d:
                del d[file]
            else:
                print("File does not exist in the previous commit to restore")
                return
            
        with open(self.index_file_path,'w') as f:
            json.dump(d,f)
        
        print(f"{file} has been removed form staging")
            
    
        

