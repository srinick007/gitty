import argparse
from repository import Repository
from index import Index

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
    group = diff_parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--head', action='store_true', dest='head',
                            help="Diff between the latest commit (HEAD) and the local directory")

    group.add_argument('--cached', action='store_true',
                            help="Diff between the index (staged changes) and the latest commit")

    group.add_argument('--all', action='store_true',
                            help="Include files that are not yet tracked but have been marked with intent-to-add")

    diff_parser.add_argument('files', nargs='*', help="Specific files to diff")

    args = parser.parse_args()
    
    repo = Repository()
    index = Index()

    if args.command == 'init':
        repo.initilization()
        print("Initializing Gitty repository...")

    elif args.command == 'commit':
        repo.commit(args.message)

    elif args.command == "status":
        print("status: ")
        index.status()
    
    elif args.command == "add":
        if args.file == ".":
            print("adding all files")
            index.add_all()
        else:
            print(f'adding file {args.file} to index')
            index.index_add(args.file)
    
    elif args.command == "restore":
        index.unstage_file(args.file)
    
    elif args.command == "branch":
        if args.branch_name == "?":
            repo.get_current_branch()
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
        elif args.files:
            print("files")
            repo.diff_files(args.files)
        else:
            print("index and local")
            repo.diff(None)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()