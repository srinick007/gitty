import json
import sys
from pathlib import Path
from difflib import unified_diff

# sys.path.append(str(Path(__file__).parent.resolve()))
from git_objects import Tree,Commit
from index import Index
from utils import get_parent_hash, read_from_blob


class Repository:
    def __init__(self):
        self.repo_path = Path.cwd().resolve()
        self.index_file_path = self.repo_path / '.git' / 'index.json'

    def initilization(self):
        Path(self.repo_path / '.git').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.git' / 'objects').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.git' / 'refs').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.git' / 'refs'/ 'heads').mkdir(parents=True, exist_ok=True)
        Path(self.repo_path / '.git' / 'HEAD').write_text('ref: refs/heads/main')
        Path(self.repo_path / '.git' / 'index.json').write_text('{}')
    
    def commit(self,commit_msg,auhtor='dhanush'):
        # creating tree struture from index
        tree = Index.construct_tree_from_json(self.index_file_path)
        # creating the tree objects
        root_tree_hash = Tree.construct_from_unflattened(tree)
        parent_hash  = get_parent_hash()

        commit = Commit(tree_hash=root_tree_hash,
                        parent_hash=parent_hash,
                        message=commit_msg,
                        author=auhtor)
        
        hash = commit.save()
        self.update_head(hash)
    
        print("all changes commited, hash: ",hash)

    def update_head(self,commit_hash):
        head_path = self.repo_path / '.git' / 'HEAD'
        content = head_path.read_text().strip()
        if content.startswith('ref'):
            ref_path = self.repo_path / '.git' / content.split(' ')[1]
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            ref_path.write_text(commit_hash)
    
    def create_branch(self,branch_name):
        parent_hash = get_parent_hash()      
        if parent_hash is None:
            print("Fatal: Not a valid object name: 'main'. (Commit something first!)")
            return
        
        new_branch_path = self.repo_path/ '.git' / 'refs' / 'heads' / branch_name
        if new_branch_path.exists():
            print(f"{branch_name} already exists")
            return

        new_branch_path.write_text(parent_hash)     
        print(f"{branch_name} created at {parent_hash}")

    def branch_checkout(self,branch_name):
        head_path = self.repo_path / '.git' / 'HEAD'
        with open(head_path,'w') as file:
            file.write(f'ref: refs/heads/{branch_name}')
        
        self.workspace_change()
        
        print(f"branch has been changed to {branch_name}")
    
    def workspace_change(self):
        commit_object = get_parent_hash()
        Commit.commit_content(commit_object)
    
    def get_current_branch(self):
        head_path = self.repo_path / '.git' / 'HEAD'
        with open(head_path,'r') as file:
            content = file.read()
        
        print(content.split(' ')[1].split('/')[-1])
        
    def log(self):
        commit_hash = get_parent_hash()

        while commit_hash:
            print("commit_hash: ",commit_hash)
            commit_content = read_from_blob(commit_hash)[1].split('\n')
            commit_hash = None
            for i in commit_content[1:]:
                if i == "":
                    continue
                content = i.split(" ")
                if content[0] == "parent":
                    commit_hash = content[1]
                    print("parent: " ,content[1])
                elif content[0] == "author":
                    print("author: ", content[1])
                else:
                    print(i)
            if commit_hash:
                print("""
                        |
                        v """)
            
    def diff(self,flag):
        if flag == 'head':
            with open(self.index_file_path,'r') as f:
                index = json.load(f)

            commit_hash = get_parent_hash()
            root_tree = read_from_blob(commit_hash)[1].split('\n')[0].split(" ")[1]
            commit_index = Tree.construct_tree_from_root_tree(root_tree)
            for key,value in commit_index.items():
                file = self.repo_path / key
                a_data = value
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

            commit_hash = get_parent_hash()
            root_tree = read_from_blob(commit_hash)[1].split('\n')[0].split(" ")[1]
            commit_index = Tree.construct_tree_from_root_tree(root_tree)
            # print(commit_index)
            for key,value in commit_index.items():
                a_data = value
                if key in index:
                    header,data = read_from_blob(index[key]['hash'])
                    b_data = data.split("\n")
                else:
                    b_data = []
                print(key)
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

        for file in self.repo_path.rglob("*") :
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
        diff = unified_diff(a, b, lineterm='')
        print('\n'.join(list(diff)))



# repo = Repository()
# repo.commit("first commit")
