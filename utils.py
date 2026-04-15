import hashlib
import json
from pathlib import Path
import time
import zlib
import regex
from difflib import SequenceMatcher

from colors import bcolors

repo_path = Path.cwd().resolve()
BLOB_PATH = repo_path/ '.gitty'/'objects'

# TODO: if the branch is manually deteled handle it
def get_current_head_hash():
    head_path = repo_path / '.gitty' / 'HEAD'
    if not head_path.exists():
        return None
    
    content = head_path.read_text().strip()

    if content.startswith('ref:'):
        ref_path = repo_path / '.gitty' / content.split(' ')[1]
        if ref_path.exists():
            return ref_path.read_text().strip()
        return None
    
    return content

# TODO: wt happens when its a detached head
def get_current_branch():
    head_path = repo_path / '.gitty' / 'HEAD'
    with open(head_path,'r') as file:
        content = file.read()
    
    if chech_sha1_hash(content):
        print(bcolors.BOLD + f"deteched head: {content}" + bcolors.ENDC)
        return

    return content.split(' ')[1].split('/')[-1]

def chech_sha1_hash(string):
    pattern = regex.compile(r'^[a-fA-F0-9]{40}$')
    if regex.match(pattern, string):
        return True
    return False

def temp_index_exist():
        path = repo_path / '.gitty' / 'temp_merge_index.json'
        return path.exists()

def delete_file_and_parent_folders(file):
    if type(file) == str:
        file = Path(file).resolve()
    if file.exists():
        file.unlink()
        for parent in file.parents:
            if parent == repo_path or parent == Path('.'):
                break

            try:
                parent.rmdir()
            except OSError:
                break

def dic_to_json(dic):
    serialized_dict = json.dumps(dic, sort_keys=True, ensure_ascii=True).encode()
    header = f"Tree {len(serialized_dict)}".encode() + b'\x00'
    full_data = header + serialized_dict
    return full_data

def convert_ctime_to_timestamp(ctime):
    struct_time = time.strptime(ctime, "%a %b %d %H:%M:%S %Y")
    timestamp = time.mktime(struct_time)

    return timestamp

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
    if type(file_content) == list:
        file_path.write_text("\n".join(file_content))
    else:
        file_path.write_text(file_content)


def read_from_blob(blob):
    folder_name,file_name = blob[:2],blob[2:]
    if len(file_name)>40:
        file_name = file_name.split(',')[0]
    with (BLOB_PATH/folder_name/file_name).open('rb') as file:
        content = file.read()
        decompressed =  zlib.decompress(content)
        content = decompressed.split(b'\x00')
        header,data = content[0].decode('utf-8'),content[1].decode('utf-8')
        return (header,data)

# print(read_from_blob('3444c58bfa6027c1935a634eed2069e3ecf3cda1'))

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
            print(key)
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

def opcode(a,b):
    s = SequenceMatcher(None, a, b)
    opcode = []
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        # print(f"{tag:7} a[{i1}:{i2}] --> b[{j1}:{j2}]")
        opcode.append(f"{tag} {i1}:{i2} {j1}:{j2}")
    return opcode

def seperate_opcode(opcode_list):
    lines_code = {}
    insertions = {}
    for opcode in opcode_list:
        tag, i_range, j_range = opcode.split(" ")
        i1, i2 = map(int, i_range.split(":"))
        j1, j2 = map(int, j_range.split(":"))

        if i1 == i2:
            insertions[i1] = f"{j1}:{j2}"
        else:
            base_indices = list(range(i1, i2))
            # How many lines in Base vs Branch?
            base_len = i2 - i1
            branch_len = j2 - j1
            
            for offset, line_idx in enumerate(base_indices):
                if offset == len(base_indices) - 1 and branch_len > base_len:
                    # If this is the LAST line of the block and Branch is longer,
                    # map the rest of the branch lines here!
                    lines_code[line_idx] = (tag, f"{j1 + offset}:{j2}")
                else:
                    lines_code[line_idx] = (tag, f"{j1 + offset}:{j1 + offset + 1}")
    return (lines_code,insertions)

def normalize_indent(lines):
    # Convert everything to 4 spaces or 8 spaces consistently
    return [line.replace('\t', '    ').expandtabs(4) for line in lines]

def gitty_helper(A_content, B_content, conflict_level, merge_branch,dont_run=False):
    temp = []   
    temp.append("<<<<<<< HEAD")
    temp.extend(A_content)
    temp.append("=======")
    temp.extend(B_content)
    temp.append(f">>>>>>> {merge_branch}")
    if dont_run == True:
        return (True, temp)
    for i in temp:
        print(i)
    if conflict_level == 1:
        print(bcolors.BLUE)
        print("IT has come to my attention that there is/are conflicts between your file")
        print("do you wish to resolve them manually(preferred) or try to solve with the help of Gitty(exprimental)")
        print("if you wish to solve with help of Gitty type 'Gitty' or type alone")
        print(bcolors.ENDC)
    elif conflict_level > 1 and conflict_level < 4:
        print(bcolors.WARNING)
        print("There is again a conflict between your file")
        print("do you wish to resolve them manually(preferred) or try to solve with the help of Gitty(exprimental)")
        print("if you wish to solve with help of Gitty type Gitty or type alone")
        print(bcolors.ENDC)
    elif conflict_level >= 4:
        print(bcolors.RED)
        print("WE MEET AGAIN FOR CONFLICT!!!")
        print("YOU KNOW THE DRILL")
        print("gitty/alone/choices/quit")

    while True:
        user_decision = input("what will be your decision (Gitty/alone):").lower()
        if user_decision in ['gitty', 'alone']:
            break
        print("invalid choice, LETS RETRY AGAIN")

    if user_decision == 'gitty':
        print(bcolors.BLUE)
        print("which version do you want to include in your file HEAD or from merging branch")
        print("enter HEAD/head for changes from HEAD or branch/BRANCH for changes from merging branch")
        print("if you want to see the conflict again enter 'choices'")
        print("if you change yout mind and want to resolve the conflict manually enter 'quit'")
        print(bcolors.ENDC)
        while True:
            user_input = input("enter the desired branch: ").lower()
            if user_input in ['head', 'branch', 'choices', 'quit']:
                break
            print("invalid choice, LETS RETRY AGAIN")
            
        if user_input == "head":
            return (False, A_content) # Conflict resolved
        elif user_input == "branch":
            return (False, B_content) # Conflict resolved
        else:
            return (True, temp) # User quit or chose alone, still a conflict
            
    else: # This is the 'alone' case, now correctly aligned
        print('you are all on your own')
        return (True, temp)

def modify_delete_conflict_helper(branch_name, blob_hash):
    while True:
        prompt = (f"{bcolors.BOLD}Conflict:{bcolors.ENDC} File was deleted in one branch and modified in another.\n"
                  f"1. {bcolors.RED}delete{bcolors.ENDC}: Discard changes and remove file.\n"
                  f"2. {bcolors.GREEN}keep{bcolors.ENDC}  : Keep modified version from {branch_name}.\n"
                  f"3. {bcolors.BLUE}later{bcolors.ENDC} : Inject markers for manual resolution.\n"
                  "Selection: ")
        
        user_decision = input(prompt).lower().strip()
        if user_decision in ['delete', 'keep', 'later']:
            break

    if user_decision == 'later':
        # Create the conflict markers for the user to edit later
        conflict_content = [
            "<<<<<<< HEAD (Deleted)",
            "======= (Modified in " + branch_name + ")",
        ]
        # Read the modified content so the user can actually see what they are "keeping"
        _, content_str = read_from_blob(blob_hash)
        conflict_content.extend(content_str.splitlines())
        conflict_content.append(f">>>>>>> {branch_name}")
        
        return {
            'action': 'CREATE_FILE',
            'conflict_status': True,
            'hash': None,
            'file_content': conflict_content
        }
        
    elif user_decision == 'keep':
        # Provide the content immediately so the handler can write it to disk
        _, content_str = read_from_blob(blob_hash)
        return {
            'action': 'KEEP',
            'conflict_status': False,
            'hash': blob_hash,
            'file_content': content_str.splitlines()
        }
        
    else: # user_decision == 'delete'
        return {
            'action': 'DELETE',
            'conflict_status': False,
            'hash': None,
            'file_content': None
        }
    


# def merge_engine(base_content,A_content,B_content,A_opcode_lines,B_opcode_lines,A_insertions,B_insertions,merge_branch):
#         # flag for conflict or not
#         overall_conflict = False
#         conflict_level = 0
#         # handling if base_content is not present
#         new_file = []
#         if not base_content:
#             temp = []
#             A1, A2 = map(int, A_insertions[0].split(":"))
#             A_new_lines = A_content[A1:A2] 
            
#             B1, B2 = map(int, B_insertions[0].split(":"))
#             B_new_lines = B_content[B1:B2] 
#             conflict_level+=1
#             conflict,new_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,merge_branch)
#             return (conflict,new_file)
        
#         i = 0 
        
#         while i<len(base_content):
#             if i in A_insertions and i in B_insertions:
#                 A1, A2 = map(int, A_insertions[i].split(":"))
#                 A_new_lines = A_content[A1:A2] # Grab all the new lines
                
#                 B1, B2 = map(int, B_insertions[i].split(":"))
#                 B_new_lines = B_content[B1:B2] # Grab all the new lines
#                 conflict_level+=1
#                 conflict,merged_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,merge_branch)
#                 if conflict:
#                     overall_conflict = conflict
#                 new_file.extend(merged_file)

#             elif i in A_insertions:
#                 insertion_range = A_insertions[i].split(":")
#                 for insert in range(int(insertion_range[0]),int(insertion_range[1])):
#                     new_file.append(A_content[insert])
#             elif i in B_insertions:
#                 insertion_range = B_insertions[i].split(":")
#                 for insert in range(int(insertion_range[0]),int(insertion_range[1])):
#                     new_file.append(B_content[insert])
            
#             A_info = A_opcode_lines.get(i)
#             B_info = B_opcode_lines.get(i)

#             if not A_info or not B_info:
#                 # If a line index is missing from the map, it's safer to treat as equal 
#                 # to avoid losing data at the end of the file
#                 new_file.append(base_content[i])
#                 i += 1
#                 continue

#             A_tag, A_coords = A_opcode_lines[i]
#             B_tag, B_coords =  B_opcode_lines[i]
#             print(f"Processing Base Line {i}: A_tag={A_tag}, B_tag={B_tag}")
#             # same opcode in both 
#             if A_tag == B_tag:
#                 if A_tag == 'equal' and B_tag == 'equal':
#                     new_file.append(base_content[i])
#                 elif A_tag == 'delete' and B_tag == 'delete':
#                     pass
#                 elif A_tag == 'replace' and B_tag == 'replace':
#                     A_j1,A_j2 = map(int, A_coords.split(":"))
#                     B_j1,B_j2 = map(int, B_coords.split(":"))
#                     if A_content[A_j1:A_j2] == B_content[B_j1:B_j2]:
#                         new_file.extend(A_content[A_j1:A_j2])
#                     else:
#                         conflict_level+=1
#                         conflict,merged_file = gitty_helper(A_content[A_j1:A_j2],B_content[B_j1:B_j2],conflict_level,merge_branch)
#                         if conflict:
#                             overall_conflict = conflict
#                         new_file.extend(merged_file)

#             # both are diff
#             elif A_tag != B_tag:
#                 if A_tag == 'equal' and B_tag == 'replace':
#                     j1, j2 = map(int, B_coords.split(":"))
#                     new_file.extend(B_content[j1:j2])
#                 elif A_tag == 'replace' and B_tag == 'equal':
#                     j1, j2 = map(int, A_coords.split(":"))
#                     print(f"DEBUG: Accessing A_content[{j1}] for Base Line {i}")
#                     new_file.extend(A_content[j1:j2])
#                 elif (A_tag == 'equal' and B_tag == 'delete') or \
#                         (A_tag == 'delete' and B_tag == 'equal'):
#                     pass
#                 elif A_tag == 'replace' and B_tag == 'delete':
#                     j1, j2 = map(int, A_coords.split(":")) # Get correct coordinate from A
#                     conflict_level+=1
#                     conflict,merged_file = gitty_helper(A_content[j1:j2],["Deleted in Branch B"],conflict_level,merge_branch)
#                     if conflict:
#                         overall_conflict = conflict
#                     new_file.extend(merged_file)

#                 elif A_tag == 'delete' and B_tag == 'replace':
#                     j1, j2 = map(int, B_coords.split(":")) # Get correct coordinate from A
#                     conflict_level+=1
#                     conflict,merged_file = gitty_helper(B_content[j1:j2],["Deleted in Branch A"],conflict_level,merge_branch)
#                     if conflict:
#                         overall_conflict = conflict
#                     new_file.extend(merged_file)

#             i+=1
        

#         if len(base_content) in A_insertions and len(base_content) in B_insertions:
#             A1, A2 = map(int, A_insertions[len(base_content)].split(":"))
#             A_new_lines = A_content[A1:A2] # Grab all the new lines
            
#             B1, B2 = map(int, B_insertions[len(base_content)].split(":"))
#             B_new_lines = B_content[B1:B2] # Grab all the new lines
#             conflict_level+=1
#             conflict,merged_file = gitty_helper([A_new_lines],[B_new_lines],conflict_level,merge_branch)
#             if conflict:
#                 overall_conflict = conflict
#             new_file.extend(merged_file)


#         elif len(base_content) in A_insertions:
#             insertion_range = A_insertions[len(base_content)].split(":")
#             for insert in range(int(insertion_range[0]),int(insertion_range[1])):
#                 new_file.append(A_content[insert])
#         elif len(base_content) in B_insertions:
#             insertion_range = B_insertions[len(base_content)].split(":")
#             for insert in range(int(insertion_range[0]),int(insertion_range[1])):
#                 new_file.append(B_content[insert])
        
#         return (overall_conflict,new_file)


# def three_way_merge(base_hash,a_hash,b_hash,branch):
    
#     base_content = read_from_blob(base_hash)[1].splitlines() if base_hash else []
#     A_content = read_from_blob(a_hash)[1].splitlines() if a_hash else []
#     B_content = read_from_blob(b_hash)[1].splitlines() if b_hash else []

#     A_content_normalized = normalize_indent(A_content)
#     B_content_normalized = normalize_indent(B_content)
#     Base_content_normalized = normalize_indent(base_content)

#     base_A_opcode = opcode(Base_content_normalized,A_content_normalized)
#     base_B_opcode = opcode(Base_content_normalized,B_content_normalized)
#     print(base_A_opcode)
#     print(base_B_opcode)
#     print(Base_content_normalized)
#     print(A_content_normalized)
#     print(B_content_normalized)
    
#     A_opcode_lines,A_insertions = seperate_opcode(base_A_opcode)
#     B_opcode_lines,B_insertions = seperate_opcode(base_B_opcode)

#     print(A_opcode_lines,A_insertions)
#     print(B_opcode_lines,B_insertions)
#     print(f"Base Length: {len(Base_content_normalized)}")
#     print(f"Branch A Length: {len(A_content_normalized)}")
#     print(f"Branch B Length: {len(B_content_normalized)}")
#     conflict_status ,merged_file = merge_engine(base_content,A_content,B_content,A_opcode_lines,
#                                             B_opcode_lines,A_insertions,B_insertions,branch)

#     for i in merged_file:
#         print(i)

# # e83c4a014af320969ecbb428403c7942eed58a54 9a3f9b4d0a8ba5e1f83f18bafe39f1a8949531a9 b34b9fcc93c1f183097b363f87d729541227a0eb
# # three_way_merge('e83c4a014af320969ecbb428403c7942eed58a54',
# #                 '9a3f9b4d0a8ba5e1f83f18bafe39f1a8949531a9',
# #                 '2bd32b42dd55d9056a3433d5a26a7c501ef7b5d2',
# #                 'branch')

# # path = Path(repo_path / 'sub_folder1' / 'sub1_folder.py')
# # print(read_and_hash_file(path).hexdigest())

# # path = Path(repo_path / 'sub_folder1' / 'sub2_folder.py')
# # print(read_and_hash_file(path).hexdigest())

# print(read_from_blob("7d753d693bced63490617d4be662470cc5e9aef9")[1])