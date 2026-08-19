from collections import deque
import json
import sys
from pathlib import Path
from difflib import unified_diff
import time
import heapq
import ctypes
import configparser

# sys.path.append(str(Path(__file__).parent.resolve()))
from gitty.colors import bcolors
from gitty.git_objects import Blob, Tree,Commit
from gitty.index import Index
from gitty.utils import chech_sha1_hash, convert_ctime_to_timestamp, delete_file_and_parent_folders, get_branch_hash, get_config_value, get_current_branch, get_current_head_hash, gitty_helper, modify_delete_conflict_helper, normalize_indent, opcode, read_from_blob, seperate_opcode, temp_index_exist, write_to_file

# TODO: maybe do reflog in future
# TODO: maybe a git ignore
class Repository:
    def __init__(self):
        self.user_home = Path.home()

    @property
    def repo_path(self) -> Path:
        return Path.cwd().resolve()

    @property
    def index_file_path(self) -> Path:
        return self.repo_path / '.gitty' / 'index.json'

    @property
    def config_path(self) -> Path:
        return self.repo_path / '.gitty' / 'config'

    @property
    def objects_path(self) -> Path:
        return self.repo_path / '.gitty' / 'objects'

    @property
    def remote_refs_path(self) ->Path:
        return self.repo_path / '.gitty' / 'refs' / 'remotes'

    @property
    def local_refs_path(self) ->Path:
        return self.repo_path / '.gitty' / 'refs' / 'heads'
    
    def initilization(self):
        Path(self.repo_path / '.gitty').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.gitty' / 'objects').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.gitty' / 'refs').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.gitty' / 'refs'/ 'heads').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.gitty' / 'HEAD').write_text('ref: refs/heads/main')
        Path(self.repo_path / '.gitty' / 'index.json').write_text('{}')

        config = configparser.ConfigParser()
        config['user'] = {}
        
        if not (self.user_home/ '.gittyconfig').exists():
            config_path  = Path(self.user_home/ '.gittyconfig')
            config = configparser.ConfigParser()
            config['user'] = {}
            with config_path.open("w") as configfile:
                config.write(configfile)

        local_config = Path(self.repo_path / '.gitty' / 'config')
        with local_config.open("w") as configfile:
            config.write(configfile)

        if sys.platform == "win32":
            ctypes.windll.kernel32.SetFileAttributesW(str(self.repo_path / '.gitty'), 2)

    def commit(self,commit_msg=None):
        author = get_config_value(self.repo_path, 'user', 'name', default='Anonymous')
        # if author is None:
        #     print("Set the author and email(optional) to commit")
        #     return
        
        merge_head = None
        is_merge = temp_index_exist()
        if not is_merge and commit_msg == None:
            print(bcolors.RED + "provide a commit message" +bcolors.ENDC)
            return 
        
        if is_merge:
            conflict_status = False
            with open(self.repo_path / '.gitty' / 'temp_merge_index.json','r') as f:
                temp_index = json.load(f)
            with open(self.index_file_path,'r') as f:
                index = json.load(f)
                
            
            for key,value in temp_index.items():
                if value['conflict_status'] == True:
                    conflict_status = True
                    print(f"There is conflict in the file {key}")
                else:
                    file = Path(key).resolve()
                    if value['action'] == 'DELETE':
                        if key in index:
                            del index[key]
                            delete_file_and_parent_folders(file)
                    else:
                        
                        if key not in index:
                            file_stat = file.stat()
                            index[key] = {'mode': "100644",
                                        'file_name':key.split('/')[-1],
                                        'ct_time':time.ctime(file_stat.st_mtime),
                                        'mt_time':time.ctime(file_stat.st_birthtime),
                                        'size':file_stat.st_size}
                        index[key]['hash'] = value['resolved_hash']

            if conflict_status == True:
                print("Resolve the conflicts and try commiting again")
                return
            
            with open(self.repo_path / '.gitty'/ 'MERGE_MSG','r') as f:
                commit_msg = f.read().strip()
                merging_branch = commit_msg.split("'")[1]
            
            with open(self.repo_path / '.gitty'/ 'MERGE_HEAD','r') as f:
                merge_head = f.read().strip()

            current_branch = get_current_branch()
            print(f"**On branch {current_branch}, currently merging {merging_branch}.**")
            
            with open(self.index_file_path,'w') as f:
                json.dump(index,f)

        # creating tree struture from index
        tree = Index.construct_tree_from_json(self.index_file_path)
        # creating the tree objects
        root_tree_hash = Tree.construct_from_unflattened(tree)
        parent_hash  = get_current_head_hash()
        
        if merge_head:
            parent_hash = parent_hash + ',' + merge_head

        commit = Commit(tree_hash=root_tree_hash,
                        parent_hash=parent_hash,
                        message=commit_msg,
                        author=author)
        
        hash = commit.save()
        self.update_head(hash)

        if is_merge:
            (self.repo_path / '.gitty' / 'temp_merge_index.json').unlink()
            (self.repo_path / '.gitty' / 'MERGE_HEAD').unlink()
            (self.repo_path / '.gitty' / 'MERGE_MSG').unlink()
            print("Merge state cleared.")

        print("all changes commited, hash: ",hash)
        return hash

    def update_head(self,commit_hash):
        head_path = self.repo_path / '.gitty' / 'HEAD'
        content = head_path.read_text().strip()
        if content.startswith('ref'):
            ref_path = self.repo_path / '.gitty' / content.split(' ')[1]
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(commit_hash)
        else:
            head_path.write_text(commit_hash)
    
    def create_branch(self,branch_name):
        parent_hash = get_current_head_hash()      
        if parent_hash is None:
            print("Fatal: Not a valid object name: 'main'. (Commit something first!)")
            return
        
        new_branch_path = self.repo_path/ '.gitty' / 'refs' / 'heads' / branch_name
        if new_branch_path.exists():
            print(f"{branch_name} already exists")
            return

        new_branch_path.write_text(parent_hash)     
        print(f"{branch_name} created at {parent_hash}")

    def list_branches(self, show_all: bool = False, show_remotes: bool = False):
        heads_dir = self.repo_path / '.gitty' / 'refs' / 'heads'
        remotes_dir = self.repo_path / '.gitty' / 'refs' / 'remotes'
        current_branch = get_current_branch()

        # List Local Branches (unless only -r was passed)
        if not show_remotes:
            if heads_dir.exists():
                local_branches = sorted([f.name for f in heads_dir.iterdir() if f.is_file()])
                for branch in local_branches:
                    if branch == current_branch:
                        print(bcolors.GREEN + f"* {branch}" + bcolors.ENDC)
                    else:
                        print(f"  {branch}")

        # List Remote-Tracking Branches (-a or -r)
        if (show_all or show_remotes) and remotes_dir.exists():
            for remote in sorted(remotes_dir.iterdir()):
                if remote.is_dir():
                    for remote_branch in sorted(remote.iterdir()):
                        if remote_branch.is_file():
                            ref_name = f"remotes/{remote.name}/{remote_branch.name}"
                            print(bcolors.FAIL + f"  {ref_name}" + bcolors.ENDC)

    # TODO: what happens when you delete a branch you are currently on
    def delete_branch(self,branch):
        branch_path = self.repo_path / '.gitty' / 'refs' / 'heads' / branch
        if not branch_path.exists():
            print(bcolors.ENDC + "branch does not exists" + bcolors.ENDC)
            return

        try:
            if branch == get_current_branch():
                print(bcolors.RED + "Cannot delete the currently checkout out branch.\n"
                      "checkout to another branch and try again" + bcolors.ENDC)
                return
            if branch_path.exists():
                branch_path.unlink()
            print(f"branch '{branch}' has been deleted")
        except:
            print(f"error has occured while deleting branch: '{branch}' ")

    def branch_checkout(self,branch_name,abort_merge=False):
        branch_name = branch_name.strip()
        if temp_index_exist() and abort_merge == False:
            print(bcolors.RED + "fatal: Merge has not been finished" + bcolors.ENDC)
            print(bcolors.RED + "Merging in progess" + bcolors.ENDC)
            print(bcolors.RED + "Resolve the conflicts (if any), stage the files (git add), and commit the merge (git commit)" + bcolors.ENDC)
            return
        current_branch = get_current_branch()
        # if current_branch == branch_name:
        #     print(f"already on branch: {branch_name}")
        #     return
        
        head_path = self.repo_path / '.gitty' / 'HEAD'

        if chech_sha1_hash(branch_name):
            head_path.write_text(branch_name)
        else:
            if branch_name == get_current_branch():
                print(f"already on '{branch_name}'")
                return
            new_branch_path = self.local_refs_path / branch_name
            if not new_branch_path.exists():
                remote_path = self.remote_refs_path / 'origin' / branch_name
                if remote_path.exists():
                    remote_hash = remote_path.read_text().strip()
                    new_branch_path.parent.mkdir(parents=True, exist_ok=True)
                    new_branch_path.write_text(remote_hash)
                    print(f"branch {branch_name} exists in remote and it is used for local")
                    head_path.write_text(f'ref: refs/heads/{branch_name}')
                    self.workspace_change()
                    return
                print(bcolors.WARNING +
                       f"""branch {branch_name} does not exist creating branch {branch_name} and  checking out""" + 
                       bcolors.ENDC)
                commit_hash = get_current_head_hash()
                if commit_hash is None:
                    print(bcolors.RED + "create a initial commit to create  branch" + bcolors.ENDC)
                    return
                new_branch_path.write_text(commit_hash)
            head_path.write_text(f'ref: refs/heads/{branch_name}')
        
        self.workspace_change()
        
        print(f"branch has been changed to {branch_name}")
    
    def workspace_change(self):
        commit_object = get_current_head_hash()
        Commit.commit_content(commit_object)
            
    
    # TODO : fix the ux issue
    def log(self):
        commit_hash = get_current_head_hash()
        seen_commit = set()
        if commit_hash is None:
            path = self.repo_path/'.gitty'/'refs'/'heads'
            if not any(path.iterdir()):
                print("Create a initial commit to view log")
            else:
                print(bcolors.RED + 
                  "fatal: your current branch has disappeared. (Did you delete it manually?)" + 
                  bcolors.ENDC)
            return
        queue = []
        commit_content = Commit.read_commit(commit_hash)
        heapq.heappush(queue,(-convert_ctime_to_timestamp(commit_content['time']),commit_hash))

        while queue:
            time_stamp,current_commit = heapq.heappop(queue)
            if current_commit in seen_commit:
                continue
            seen_commit.add(current_commit)

            print('\033[94m'+"commit_hash: ",current_commit+'\033[0m')
            commit_content = Commit.read_commit(current_commit)
            
            if "parent" in commit_content:
                print(f"Merge: {' '.join(commit_content['parent'])}" if len(list(commit_content['parent'])) > 1 else f"parent: {commit_content['parent'][0]}")
                for parent_hash in commit_content['parent']:
                    parent_commit_content = Commit.read_commit(parent_hash)
                    heapq.heappush(queue,(-convert_ctime_to_timestamp(parent_commit_content['time']),parent_hash))
            
            print(f"Author: {commit_content.get('author', 'Unknown')}")
            print(f"Date:   {commit_content.get('time', 'Unknown')}")
            print(f"\n    {commit_content.get('message', '')}\n")
            if queue:
                print("    |\n    v\n")
        
    def diff(self,flag):
        if flag == 'head':
            with open(self.index_file_path,'r') as f:
                index = json.load(f)

            commit_hash = get_current_head_hash()
            root_tree = Commit.read_commit(commit_hash)['tree']
            commit_index = Tree.construct_index_from_root_tree(root_tree)
            for key,value in commit_index.items():
                file = self.repo_path / key
                a_data = read_from_blob(value['hash'])[1].split("\n")
                if file.exists():
                    with open(file,'r') as f:
                        content = f.read()
                        
                    b_data = content.split("\n")
                else:
                    b_data = []
                print(key)
                self.diff_between_files(a_data,b_data)

        elif flag == "cached":
            with open(self.index_file_path,'r') as f:
                index = json.load(f)

            commit_hash = get_current_head_hash()
            root_tree = Commit.read_commit(commit_hash)['tree']
            commit_index = Tree.construct_index_from_root_tree(root_tree)
            # print(commit_index)
            for key,value in commit_index.items():
                a_data = read_from_blob(value['hash'])[1].split("\n")
                if key in index:
                    header,data = read_from_blob(index[key]['hash'])
                    b_data = data.split("\n")
                else:
                    b_data = []
                self.diff_between_files(a_data,b_data)
        else:
            with open(self.index_file_path,'r') as f:
                index = json.load(f)
            
            for key,value in index.items():
                file = self.repo_path / key
                header,data = read_from_blob(value['hash'])
                a_data = data.split("\n")
                if file.exists():
                    with open(file,'r') as f:
                        content = f.read()
                        
                    b_data = content.split("\n")
                else:
                    b_data = []
                print(key)
                self.diff_between_files(a_data,b_data)
    
    def diff_intent_to_add(self):
        with open(self.index_file_path,'r') as f:
                index = json.load(f)

        for file in self.repo_path.rglob("*"):
            if not any(part.startswith('.') for part in file.parts):
                if file.is_file():
                    file = Path(file).resolve()
                    rel_key = file.relative_to(self.repo_path).as_posix()
                    with open(file,'r') as f:
                        file_content = f.read()
                    b_data = file_content.split("\n")

                    if rel_key in index:
                        file = self.repo_path / rel_key
                        header,data = read_from_blob(index[rel_key]['hash'])
                        a_data = data.split("\n")
                    else:
                        a_data = []
                    
                    print(rel_key)
                    self.diff_between_files(a_data,b_data)    

    def diff_files(self,files):
        with open(self.index_file_path,'r') as f:
                index = json.load(f)

        for file in files:
            if file in index:
                header,data = read_from_blob(index[file]["hash"])
                a_data = data.split("\n")
            else:
                a_data = []
            
            file_path = self.repo_path / file
            if file_path.exists():
                with open(file,'r') as f:
                    content = f.read()
                    
                b_data = content.split("\n")
            else:
                b_data = []
            print(file)
            self.diff_between_files(a_data,b_data)    

    def diff_between_files(self,a,b):
        diff = unified_diff(a, b, n=3,lineterm='')
        for line in diff:
            if line.startswith('+'):
                print(f"{bcolors.GREEN}{line}{bcolors.ENDC}")
            elif line.startswith('-'):
                print(f"{bcolors.RED}{line}{bcolors.ENDC}")
            elif line.startswith('^'):
                print(f"{bcolors.BLUE}{line}{bcolors.ENDC}")
            else:
                print(line)

    @staticmethod
    def get_previous_commit_hash(command):
        commit_hash = get_current_head_hash()
        commit_content = Commit.read_commit(commit_hash)
        print("current hash: ", commit_hash)
        for previous_commit in range(int(command.split('~')[1])):
            
            commit_parent = commit_content.get('parent',None)
            if commit_parent:
                commit_parent = commit_parent[0]
                commit_content = Commit.read_commit(commit_parent)
            else:
                print(bcolors.RED + "not enough parent commit to go back" + bcolors.ENDC)
                return
            
        print(bcolors.CYAN + F"parent hash: {commit_parent}" + bcolors.ENDC)
        return commit_parent
    
    def soft_reset(self,command):
        commit_parent_hash = Repository.get_previous_commit_hash(command)
        if commit_parent_hash == None:
            return
        self.update_head(commit_parent_hash)
    
    def mixed_rest(self,command):
        commit_parent_hash = Repository.get_previous_commit_hash(command)
        if commit_parent_hash == None:
            return
        root_tree = Commit.read_commit(commit_parent_hash)['tree']
        commit_index = Tree.construct_index_from_root_tree(root_tree)
        for key,value in commit_index.items():
            file = self.repo_path / key
            ct_time = time.ctime(time.time())
            if file.exists():
                file_stat = file.stat()
                ct_time = time.ctime(file_stat.st_birthtime )
                file_size = file_stat.st_size
            else:
                file_size = len(read_from_blob(value['hash'])[1])

            commit_index[key] = {'hash':value['hash'],
                                    'ct_time':ct_time,
                                    'mt_time':ct_time,
                                    'size':file_size,
                                    'mode': "100644",
                                    'file_name':file.name}

        self.update_head(commit_parent_hash)
        with open(self.index_file_path,'w') as f:
            json.dump(commit_index,f)

    def hard_reset(self,command):   
        commit_parent_hash = Repository.get_previous_commit_hash(command)
        if commit_parent_hash == None:
            return
        Commit.commit_content(commit_parent_hash)
        self.update_head(commit_parent_hash)
    
    # TODO : changing reading commit content logic when 2 parents are present add a -m arg
    def cherry_pick(self,commit_hash,no_commit,commit_message,parent=0):
        commit_content = Commit.read_commit(commit_hash)
        if len(commit_content['parent']) == 2 and parent == 0:
            print(bcolors.WARNING+ "cherry picking merge commit requries which parent commit to either parent 1 or parent 2"+bcolors.ENDC)
            return
        root_tree = commit_content['tree']
        # if no parent
        parent_commit_index = {}
        # if parent is present
        if "parent" in commit_content:
            parent_commit_hash = commit_content['parent'][parent]
            # which parent_commit_hash to look for?

            parent_commit_content = Commit.read_commit(parent_commit_hash)
            parent_root_tree = parent_commit_content['tree']
            parent_commit_index = Tree.construct_index_from_root_tree(parent_root_tree)

        commit_index = Tree.construct_index_from_root_tree(root_tree)

        diff_index = {}
        for key,value in commit_index.items():
            if key in parent_commit_index:
                if value['hash'] != parent_commit_index[key]['hash']:
                    diff_index[key] = value
                    diff_index[key]['modify_type'] = "add"
                    del parent_commit_index[key]
                else:
                    del parent_commit_index[key]
            elif key not in parent_commit_index:
                diff_index[key] = value
                diff_index[key]['modify_type'] = "add"
        
        for key,value in parent_commit_index.items():
            diff_index[key] = value
            diff_index[key]['modify_type'] = "delete"

        with open(self.index_file_path,'r') as f:
            index = json.load(f)
        # print(diff_index)
        for key,value in diff_index.items():
            if value['modify_type'] == "add":
                file = self.repo_path / key
                if not file.exists():
                    file_header,file_contents = read_from_blob(value['hash'])
                    write_to_file(file,file_contents)
                file_size = len(read_from_blob(value['hash'])[1])
                index[key] = {'hash':value['hash'],
                                'ct_time':time.ctime(time.time()),
                                'mt_time':time.ctime(time.time()),
                                'size':file_size,
                                'mode': "100644",
                                'file_name': key.split("/")[-1]}
            elif value['modify_type'] == "delete":
                if key in index:
                    file_path = Commit.repo_path / key
                    file_path.unlink(missing_ok=False)
                    for parent in file_path.parents:
                        if parent == self.repo_path or parent == Path('.'):
                            break

                        try:
                            parent.rmdir()
                        except OSError:
                            break
                    del index[key]
        
        with open(self.index_file_path,'w') as f:
            json.dump(index,f)
        
        # default is commit when cherry picking. only dont commit and make changes to working dir when no_commit is True
        if no_commit == False:
            message = commit_message if commit_message else commit_content['message']
            self.commit(message)        
            print(bcolors.GREEN + f"cherry picked from commit {commit_hash}"+bcolors.ENDC)
        else:
            print(bcolors.GREEN + f"successfully cherry picked from commit {commit_hash} and applied changed to working dir"+bcolors.ENDC)



    def lca(self,commit_1,commit_2):
        queue = []
        heapq.heapify(queue)
        commit_1_content = Commit.read_commit(commit_1)
        commit_2_content = Commit.read_commit(commit_2)

        stash = {}

        heapq.heappush(queue,(-convert_ctime_to_timestamp(commit_1_content['time']),commit_1,1))
        heapq.heappush(queue,(-convert_ctime_to_timestamp(commit_2_content['time']),commit_2,2))

        while queue:
            time_stamp,current_commit,current_tag = heapq.heappop(queue)

            existing_commit = stash.get(current_commit,0)

            while existing_commit != 0 and existing_commit != current_tag:
                return current_commit

            if existing_commit == 0:
                stash[current_commit] = current_tag
            
            commit_content = Commit.read_commit(current_commit)
            if 'parent' in commit_content:
                for parent in commit_content['parent']:
                    timestamp = convert_ctime_to_timestamp(commit_content['time'])
                    heapq.heappush(queue,(-timestamp,parent,current_tag))
    
    def _apply_merge_change(self, rel_path, action, is_conflict, content=None, known_hash=None, msg=""):
        """Physically updates the disk and returns the hash if clean."""
        full_path = self.repo_path / rel_path
        
        if action in ["CREATE_FILE", "KEEP"]:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            write_to_file(full_path, content)
            
            if not is_conflict:
                return known_hash if known_hash else Blob(full_path).save()
            return None

        elif action == "DELETE":
            delete_file_and_parent_folders(full_path)
            return None
    
    def _write_merge_metadata(self, merge_head, branch_name, temp_index):
        """Saves the merge state to the .gitty directory."""
        (self.repo_path / '.gitty' / 'MERGE_HEAD').write_text(merge_head)
        (self.repo_path / '.gitty' / 'MERGE_MSG').write_text(f"Merge branch '{branch_name}'")
        
        with open(self.repo_path / '.gitty' / 'temp_merge_index.json', 'w') as f:
            json.dump(temp_index, f, indent=4)
        
        conflicts = sum(1 for v in temp_index.values() if v['conflict_status'])
        if conflicts > 0:
            print(f"\nAutomatic merge failed; fix {conflicts} conflicts and then commit.")
        else:
            print("\nAutomatic merge successful. Use 'gitty commit' to finish.")

    def merge_engine(base_content,A_content,B_content,A_opcode_lines,B_opcode_lines,A_insertions,B_insertions,branch_name,dont_run_helper=False):
        # flag for conflict or not
        overall_conflict = False
        conflict_level = 0
        # handling if base_content is not present
        new_file = []
        if not base_content:
            A1, A2 = map(int, A_insertions[0].split(":"))
            A_new_lines = A_content[A1:A2] 
            
            B1, B2 = map(int, B_insertions[0].split(":"))
            B_new_lines = B_content[B1:B2] 
            conflict_level+=1
            conflict,new_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,branch_name,dont_run_helper)
            return (conflict,new_file)
        
        i = 0 
        
        while i<len(base_content):
            if i in A_insertions and i in B_insertions:
                A1, A2 = map(int, A_insertions[i].split(":"))
                A_new_lines = A_content[A1:A2] # Grab all the new lines
                
                B1, B2 = map(int, B_insertions[i].split(":"))
                B_new_lines = B_content[B1:B2] # Grab all the new lines
                conflict_level+=1
                conflict,merged_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,dont_run_helper)
                if conflict:
                    overall_conflict = conflict
                new_file.extend(merged_file)

            elif i in A_insertions:
                insertion_range = A_insertions[i].split(":")
                for insert in range(int(insertion_range[0]),int(insertion_range[1])):
                    new_file.append(A_content[insert])
            elif i in B_insertions:
                insertion_range = B_insertions[i].split(":")
                for insert in range(int(insertion_range[0]),int(insertion_range[1])):
                    new_file.append(B_content[insert])
            
            A_info = A_opcode_lines.get(i)
            B_info = B_opcode_lines.get(i)

            if not A_info or not B_info:
                new_file.append(base_content[i])
                i += 1
                continue

            A_tag, A_coords = A_opcode_lines[i]
            B_tag, B_coords =  B_opcode_lines[i]
            # print(A_tag,B_tag)
            # same opcode in both 
            if A_tag == B_tag:
                if A_tag == 'equal' and B_tag == 'equal':
                    new_file.append(base_content[i])
                elif A_tag == 'delete' and B_tag == 'delete':
                    pass
                elif A_tag == 'replace' and B_tag == 'replace':
                    A_j1,A_j2 = map(int, A_coords.split(":"))
                    B_j1,B_j2 = map(int, B_coords.split(":"))
                    if A_content[A_j1:A_j2] == B_content[B_j1:B_j2]:
                        new_file.extend(A_content[A_j1:A_j2])
                    else:
                        conflict_level+=1
                        conflict,merged_file = gitty_helper(A_content[A_j1:A_j2],B_content[B_j1:B_j2],conflict_level,branch_name,dont_run_helper)
                        if conflict:
                            overall_conflict = conflict
                        new_file.extend(merged_file)

            # both are diff
            elif A_tag != B_tag:
                if A_tag == 'equal' and B_tag == 'replace':
                    j1, j2 = map(int, B_coords.split(":"))
                    new_file.extend(B_content[j1:j2])
                elif A_tag == 'replace' and B_tag == 'equal':
                    j1, j2 = map(int, A_coords.split(":"))
                    new_file.extend(A_content[j1:j2])
                elif (A_tag == 'equal' and B_tag == 'delete') or \
                        (A_tag == 'delete' and B_tag == 'equal'):
                    pass
                elif A_tag == 'replace' and B_tag == 'delete':
                    j1, j2 = map(int, A_coords.split(":")) # Get correct coordinate from A
                    conflict_level+=1
                    conflict,merged_file = gitty_helper(A_content[j1:j2],["Deleted in Branch B"],conflict_level,dont_run_helper)
                    if conflict:
                        overall_conflict = conflict
                    new_file.extend(merged_file)

                elif A_tag == 'delete' and B_tag == 'replace':
                    j1, j2 = map(int, B_coords.split(":")) # Get correct coordinate from A
                    conflict_level+=1
                    conflict,merged_file = gitty_helper(B_content[j1:j2],["Deleted in Branch A"],conflict_level,dont_run_helper)
                    if conflict:
                        overall_conflict = conflict
                    new_file.extend(merged_file)

            i+=1
        

        if len(base_content) in A_insertions and len(base_content) in B_insertions:
            A1, A2 = map(int, A_insertions[len(base_content)].split(":"))
            A_new_lines = A_content[A1:A2] # Grab all the new lines
            
            B1, B2 = map(int, B_insertions[len(base_content)].split(":"))
            B_new_lines = B_content[B1:B2] # Grab all the new lines
            conflict_level+=1
            conflict,merged_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,dont_run_helper)
            if conflict:
                overall_conflict = conflict
            new_file.extend(merged_file)


        elif len(base_content) in A_insertions:
            insertion_range = A_insertions[len(base_content)].split(":")
            for insert in range(int(insertion_range[0]),int(insertion_range[1])):
                new_file.append(A_content[insert])
        elif len(base_content) in B_insertions:
            insertion_range = B_insertions[len(base_content)].split(":")
            for insert in range(int(insertion_range[0]),int(insertion_range[1])):
                new_file.append(B_content[insert])
        
        return (overall_conflict,new_file)


    def three_way_merge(base_hash,a_hash,b_hash,branch, dont_run_helper=False):

        base_content = read_from_blob(base_hash)[1].splitlines() if base_hash else []
        A_content = read_from_blob(a_hash)[1].splitlines() if a_hash else []
        B_content = read_from_blob(b_hash)[1].splitlines() if b_hash else []

        A_content_normalized = normalize_indent(A_content)
        B_content_normalized = normalize_indent(B_content)
        Base_content_normalized = normalize_indent(base_content)

        base_A_opcode = opcode(Base_content_normalized,A_content_normalized)
        base_B_opcode = opcode(Base_content_normalized,B_content_normalized)
      
        
        A_opcode_lines,A_insertions = seperate_opcode(base_A_opcode)
        B_opcode_lines,B_insertions = seperate_opcode(base_B_opcode)

        conflict_status ,merged_file = Repository.merge_engine(base_content,A_content,B_content,A_opcode_lines,
                                                B_opcode_lines,A_insertions,B_insertions,branch,dont_run_helper)
        # for i in merged_file:
        #     print(i)
        
        return (conflict_status,merged_file)


    def _create_temp_entry(self, action, conflict, b, h, m, r=None):
        """Utility to keep the dictionary schema consistent."""
        return {
            'action': action,
            'conflict_status': conflict,
            'base_hash': b,
            'head_hash': h,
            'merge_hash': m,
            'resolved_hash': r
        }

    def merge(self, branch_name: str, base_branch: str = None):
        # Parse origin prefix
        is_origin = False
        if branch_name.startswith("origin/"):
            is_origin = True
            branch_name = branch_name.split("/", 1)[1]

        # Determine base branch
        active_branch = get_current_branch()
        if base_branch is None:
            base_branch = active_branch
        
        target_branch = branch_name

        # Prevent merging a branch into itself
        if not is_origin and base_branch == target_branch:
            print(f"Already on '{base_branch}'.\nNothing to merge.")
            return

        # Resolve base branch commit hash
        current_head = get_branch_hash(base_branch)
        if not current_head:
            # Fall back to raw HEAD if in detached HEAD state
            current_head = get_current_head_hash()

        # Resolve target commit hash (merge_head)
        if not chech_sha1_hash(branch_name):
            if is_origin:
                ref_path = self.repo_path / '.gitty' / 'refs' / 'remotes' / 'origin' / branch_name
            else:
                ref_path = self.repo_path / '.gitty' / 'refs' / 'heads' / branch_name

            if not ref_path.exists():
                print(f"{bcolors.RED}Branch '{branch_name}' not found.{bcolors.ENDC}")
                return
            
            merge_head = ref_path.read_text().strip()
        else:
            merge_head = branch_name

        # Direct identity check
        if current_head == merge_head:
            print("Already up to date.")
            return

        # Find Lowest Common Ancestor (LCA)
        base_commit = self.lca(current_head, merge_head)

        # Case A: Target is already behind base
        if base_commit == merge_head:
            print("Already up to date (current branch is ahead).")
            return

        # Case B: Fast-Forward
        if base_commit == current_head:
            print(f"Updating {current_head[:7]}..{merge_head[:7]}")
            print(f"Fast-forward to '{branch_name}'")
            
            # Advance the local branch pointer
            branch_ref_path = self.repo_path / '.gitty' / 'refs' / 'heads' / base_branch
            branch_ref_path.parent.mkdir(parents=True, exist_ok=True)
            branch_ref_path.write_text(f"{merge_head}\n")
            
            # Update working directory ONLY if base_branch is the active HEAD
            if base_branch == active_branch:
                self.workspace_change()
            return

        # Case C: 3-Way Merge (Diverged)
        print(f"Auto-merging (3-way merge base: {base_commit[:7]})...")
        # Load all 3 indexes into memory
        base_idx = Tree.construct_index_from_root_tree(Commit.read_commit(base_commit)['tree'])
        head_idx = Tree.construct_index_from_root_tree(Commit.read_commit(current_head)['tree'])
        merge_idx = Tree.construct_index_from_root_tree(Commit.read_commit(merge_head)['tree'])

        temp_merge_index = {}
        all_paths = set(base_idx.keys()) | set(head_idx.keys()) | set(merge_idx.keys())

        for path in all_paths:
            base = base_idx.get(path, {}).get('hash')
            head = head_idx.get(path, {}).get('hash')
            remot = merge_idx.get(path, {}).get('hash')

            # 1. Identical changes or no changes
            if head == remot:
                continue 

            # 2. Changed in Remote, unchanged in HEAD (Auto-merge remote)
            elif base == head and base != remot:
                if remot: # Modified or Added in Remote
                    print("<<<<")
                    content = read_from_blob(remot)[1].splitlines()
                    self._apply_merge_change(path, "CREATE_FILE", False, content, remot, "Updated from remote")
                    temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", False, base, head, remot, remot)
                else: # Deleted in Remote
                    print(">>>>")
                    self._apply_merge_change(path, "DELETE", False)
                    temp_merge_index[path] = self._create_temp_entry("DELETE", False, base, head, remot, None)

            # 3. Changed in HEAD, unchanged in Remote (Keep HEAD)
            elif base == remot and base != head:
                # Head already has the correct file, just record the state
                temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", False, base, head, remot, head)

            # 4. Modified in both (Content Merge)
            elif base and head and remot:
                print(f"Auto-merging {path}")
                is_conflict, content = Repository.three_way_merge(base, head, remot, branch_name)
                res_hash = self._apply_merge_change(path, "CREATE_FILE", is_conflict, content)
                temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", is_conflict, base, head, remot, res_hash)

            # 5. Modify/Delete Conflict
            elif base and (not head or not remot):
                print(f"{bcolors.WARNING}CONFLICT (modify/delete): {path}{bcolors.ENDC}")
                # Use your helper to ask user
                decision = modify_delete_conflict_helper(branch_name, head or remot)
                res_hash = self._apply_merge_change(path, decision['action'], decision['conflict_status'], decision.get('file_content'))
                temp_merge_index[path] = self._create_temp_entry(decision['action'], decision['conflict_status'], base, head, remot, res_hash)

            # 6. Both added (New files in both)
            elif not base and head and remot:
                print(f"Conflict: Both added {path}")
                is_conflict, content = Repository.three_way_merge(None, head, remot, branch_name)
                res_hash = self._apply_merge_change(path, "CREATE_FILE", is_conflict, content)
                temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", is_conflict, base, head, remot, res_hash)
           
            # 7. Additions: Present in only one branch, no common ancestor
            elif not base:
                # Case: Added only in Remote (Accept it)
                if remot and not head:
                    print(f"Adding {path} from remote")
                    content = read_from_blob(remot)[1].splitlines()
                    self._apply_merge_change(path, "CREATE_FILE", False, content, remot)
                    temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", False, None, None, remot, remot)

            # Case: Added only in HEAD (Keep it)
            elif head and not remot:
                # File is already on disk, just record it in temp index
                temp_merge_index[path] = self._create_temp_entry("CREATE_FILE", False, None, head, None, head)

        # Finalize state
        self._write_merge_metadata(merge_head, branch_name, temp_merge_index)


    def merge_abort(self):
        current_branch = get_current_branch()
        self.branch_checkout(current_branch,abort_merge=True)
        files_to_delete = ['temp_merge_index.json','MERGE_HEAD','MERGE_MSG']
        for file in files_to_delete:
            file_path = self.repo_path / '.gitty' / file
            file_path.unlink(missing_ok=True)
        return
    
    def diff_merge_aware(self,file_paths,side = "ours"):
        
        temp_index = self.repo_path / '.gitty' / 'temp_merge_index.json'

        if temp_index_exist() == False:
            print("No merge in Progress")
            return

        with open(temp_index, 'r') as f:
            index = json.load(f)

        if not file_paths:
            file_paths = [key for key,value in index.items() if value['conflict_status'] == True]

        for file_path in file_paths:
            rel_path = Path(file_path).resolve().relative_to(self.repo_path).as_posix()
            
            entry = index.get(rel_path)
            if not entry:
                print(f"File {rel_path} was not involved in the merge.")
                return
        
            target_hash = entry['head_hash'] if side == "ours" else entry['merge_hash']

            if not target_hash:
                print(f"No {side} version exists for this file (it might have been created in the other branch).")
                return

            _, content = read_from_blob(target_hash)
            clean_content = content.splitlines()

            with open(rel_path , 'r') as f:
                working_file = f.read().splitlines()
            print(bcolors.BOLD + rel_path + bcolors.ENDC)
            self.diff_between_files(clean_content,working_file)

    def unstage_merge(self, file):
        
        with open(self.repo_path / '.gitty'/ 'temp_merge_index.json','r') as f:
            temp_index = json.load(f)

        file = Path(file).resolve()
        rel_path = file.relative_to(self.repo_path).as_posix()

        entry = temp_index.get(rel_path)
        if not entry:
            Index.unstage_file(file)
            return
        
        if entry['action'] == 'DELETE':
            head_hash = entry.get('head_hash')
            merge_hash = entry.get('merge_hash')

            restoring_hash = merge_hash if head_hash is None else head_hash
            
            _, content = read_from_blob(restoring_hash)
            write_to_file(file,content)
            temp_index[rel_path]['action'] = 'CREATE_FILE'
            temp_index[rel_path]['conflict_status'] = True
            temp_index[rel_path]['resolved_hash'] = None

        elif entry['action'] == 'KEEP':
            temp_index[rel_path]['action'] = 'CREATE_FILE'
            temp_index[rel_path]['conflict_status'] = True
            temp_index[rel_path]['resolved_hash'] = None
        
        else:
            base = entry.get('base_hash')
            head = entry.get('head_hash')
            remot = entry.get('merge_hash')
            with open(self.repo_path / '.gitty' / 'MERGE_MSG','r') as f:
                msg_content = f.read()
            

            if base is None and remot is None:
                temp_index[rel_path]['conflict_status'] = True
                temp_index[rel_path]['resolved_hash'] = None

                print(f"Unstaged {rel_path} (No merge conflict detected for this file).")
            elif base is None and head is None and remot:
                temp_index[rel_path]['conflict_status'] = True
                temp_index[rel_path]['resolved_hash'] = None
                
                if file.exists():
                    file.unlink()
                    for parent in file.parents:
                        if parent == self.repo_path or parent == Path('.'):
                            break

                        try:
                            parent.rmdir()
                        except OSError:
                            break
                
                print(f"Unstaged {rel_path} (Removed new file introduced by remote branch).")
            else:
                branch_name = msg_content.split(" ")[-1].replace("'", "") if " " in msg_content else "MERGE_OBJ"
                is_conflict, content = Repository.three_way_merge(base, head, remot, branch_name,dont_run_helper = True)   
                res_hash = self._apply_merge_change(rel_path, "CREATE_FILE", True, content)
                temp_index[rel_path]['action'] = 'CREATE_FILE'
                temp_index[rel_path]['conflict_status'] = True
                temp_index[rel_path]['resolved_hash'] = None

        with open(self.repo_path / '.gitty'/ 'temp_merge_index.json','w') as f:
            json.dump(temp_index,f)

    def remote_add(self, name: str, url: str):
        """Adds a new remote entry into .gitty/config."""
        if not self.config_path.parent.exists():
            print(bcolors.RED + "fatal: not a gitty repository (or any of the parent directories)" + bcolors.ENDC)
            return

        config = configparser.ConfigParser()
        if self.config_path.exists():
            config.read(self.config_path)

        section_name = f'remote "{name}"'

        # Check if remote alias already exists
        if config.has_section(section_name):
            print(bcolors.RED + f"fatal: remote {name} already exists." + bcolors.ENDC)
            return

        # Validate URL/Path format (e.g., author/repo_name)
        clean_url = url.strip().strip("'\"")
        if "/" not in clean_url:
            print(bcolors.RED + f"fatal: invalid remote url format '{url}'. Expected 'username/repo_name'" + bcolors.ENDC)
            return

        config.add_section(section_name)
        config.set(section_name, 'url', clean_url)

        # Write to .gitty/config
        with open(self.config_path, 'w') as f:
            config.write(f)

        print(bcolors.GREEN + f"Added remote '{name}' -> {clean_url}" + bcolors.ENDC)

    def remote_list(self, verbose: bool = False):
        """Lists all configured remotes (equivalent to git remote -v)."""
        if not self.config_path.exists():
            return

        config = configparser.ConfigParser()
        config.read(self.config_path)

        remotes = {}
        for section in config.sections():
            if section.startswith('remote "') and section.endswith('"'):
                name = section[8:-1]
                url = config.get(section, 'url', fallback='')
                remotes[name] = url

        if not remotes:
            return

        for name, url in remotes.items():
            if verbose:
                print(f"{name}\t{url} (fetch)")
                print(f"{name}\t{url} (push)")
            else:
                print(name)

    def remote_remove(self, name: str):
        """Removes a remote and its tracking branches."""
        if not self.config_path.exists():
            return

        config = configparser.ConfigParser()
        config.read(self.config_path)
        section_name = f'remote "{name}"'

        if not config.has_section(section_name):
            print(bcolors.RED + f"fatal: No such remote: '{name}'" + bcolors.ENDC)
            return

        config.remove_section(section_name)
        with open(self.config_path, 'w') as f:
            config.write(f)

        print(f"Removed remote '{name}'.")