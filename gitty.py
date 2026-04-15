import argparse
from repository import Repository
from index import Index
from utils import get_current_branch, temp_index_exist

def main():
    parser = argparse.ArgumentParser(description='Gitty: A Python Git Clone')
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    subparsers.add_parser('init', help='Initialize a new Gitty repository')

    commit_parser = subparsers.add_parser('commit', help='Commit staged changes')
    commit_parser.add_argument('message', type=str, help='The commit message')

    subparsers.add_parser('status', help='shows the diff between the working dir and index')

    index_parser = subparsers.add_parser('add', help="""add files to index. either add a single file ex: git add <relative file path>
                                                             or add all the files ex: git add .""")
    index_parser.add_argument('file', type=str, help="single file or all the files")

    branch_parser = subparsers.add_parser('branch', help="create new branch")
    branch_parser.add_argument('branch_name', type=str, help="name of the branch")

    checkout_parser = subparsers.add_parser('checkout', help="checkout to branch")
    checkout_parser.add_argument('branch_name', type=str, help="branch to checkout to")

    subparsers.add_parser('log', help="print the commit history")

    unstage_parser = subparsers.add_parser('restore', help="unstage the file from index")
    unstage_parser.add_argument('file', type=str, help="specify a single file or '.' for all the file")

    diff_parser = subparsers.add_parser('diff', help="Show changes between commits, commit and working tree, etc.")
    diff_group = diff_parser.add_mutually_exclusive_group(required=False)
    diff_group.add_argument('--head', action='store_true', dest='head',
                            help="Diff between the latest commit (HEAD) and the local directory")

    diff_group.add_argument('--cached', action='store_true',
                            help="Diff between the index (staged changes) and the latest commit")

    diff_group.add_argument('--all', action='store_true',
                            help="Include files that are not yet tracked but have been marked with intent-to-add")    
    diff_group.add_argument('--ours', action='store_true',
                            help="Include files that are not yet tracked but have been marked with intent-to-add")    
    diff_group.add_argument('--theirs', action='store_true',
                            help="Include files that are not yet tracked but have been marked with intent-to-add")    

    diff_parser.add_argument('files', nargs='*', help="Specific files to diff seperated by a <space>")
    
    reset_parser = subparsers.add_parser('reset', help="Reset current HEAD to the specified state")
    reset_group = reset_parser.add_mutually_exclusive_group(required=True)
    reset_group.add_argument("--soft", action="store_true", help="Resets without touching index or working tree")
    reset_group.add_argument("--mixed", action="store_true", help="Resets index but not working tree (default)")
    reset_group.add_argument("--hard", action="store_true", help="Resets index and working tree (all changes discarded)")

    reset_parser.add_argument("commit", nargs="?", default="HEAD~1", help="The commit to reset to")

    cherry_parser= subparsers.add_parser("cherry-pick", help="""cherry pick the changes you want from a 
                                                               particular commit and add to your current working directory""")    
    cherry_group = cherry_parser.add_mutually_exclusive_group(required=False)
    cherry_group.add_argument("--no-commit", action='store_true', help="dont commit the changes just change the working dir")
    cherry_group.add_argument('-e', type=str, help="add commit message")
    cherry_group.add_argument('-m', type=int, default=0, help="add commit message")
    cherry_parser.add_argument("commit_hash", type=str, help="commit hash of the commit you want changes from")


    merge_parser = subparsers.add_parser('merge', help="merge the current branch with the specified branch")
    merge_group = merge_parser.add_mutually_exclusive_group(required=True)
    merge_group.add_argument('--abort', action='store_true', help="abort the merges and changes the workplace to branch in HEAD")
    merge_group.add_argument('merging_branch', nargs="?", help="branch that you want to merge with the current branch")

    args = parser.parse_args()
    
    repo = Repository()
    index = Index()

    if args.command == 'init':
        repo.initilization()
        print("Initializing Gitty repository...")

    elif args.command == 'commit':
        repo.commit(args.message)

    elif args.command == "status":
        index.status()
    
    elif args.command == "add":
        if args.file == ".":
            print("adding all files")
            index.add_all()
        else:
            print(f'adding file {args.file} to index')
            index.index_add(args.file)
    
    elif args.command == "restore":
        if temp_index_exist():
            repo.unstage_merge(args.file)
        else:
            index.unstage_file(args.file)
    
    elif args.command == "branch":
        if args.branch_name == "?":
            print(f"Branch in HEAD: {get_current_branch()}")
            return
        repo.create_branch(args.branch_name)

    elif args.command == "checkout":
        repo.branch_checkout(args.branch_name)

    elif args.command == "log":
        repo.log()
    
    elif args.command == "diff":
        if args.head:
            print("head and local")
            repo.diff("head")
        elif args.cached:
            print("head and index")
            repo.diff("cached")
        elif args.all:
            print("index and all local")
            repo.diff_intent_to_add()
        elif args.ours or args.theirs:
            if args.ours and args.files:
                repo.diff_merge_aware(args.files, 'ours')
            elif args.ours and not args.files:
                repo.diff_merge_aware(None, 'ours')
            elif args.theirs and args.files:
                repo.diff_merge_aware(args.files, 'thiers')
            elif args.theirs and not args.files:
                repo.diff_merge_aware(None, 'thiers')
        elif args.files:
            print("files")
            repo.diff_files(args.files)
        else:
            print("index and local")
            repo.diff(None)

    elif args.command == "reset":
        if not args.commit.split('~')[-1].isnumeric():
            print('Invalid value for commit history')
            return
        if args.soft:
            print("resetting soft")
            repo.soft_reset(args.commit)
        elif args.mixed:
            print("resetting mixed")
        elif args.hard:
            print("resetting hard")
            repo.hard_reset(args.commit)
        else:
            repo.mixed_rest(args.commit)

    elif args.command == "cherry-pick":
        repo.cherry_pick(args.commit_hash,args.no_commit,args.e,args.m)
    
    elif args.command == "merge":
        if args.merging_branch:
            repo.merge(args.merging_branch)
        elif args.abort:
            repo.merge_abort()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()