import argparse
import asyncio
from pathlib import Path
import sys
from gitty.backend import Gitty_hub
from gitty.colors import bcolors
from gitty.repository import Repository
from gitty.index import Index
from gitty.utils import get_current_branch, temp_index_exist

EXEMPT_COMMANDS = {"init", "clone", "version", "help", None}

def check_gitty_repo(repo_path: Path = None) -> bool:
    target = repo_path or Path.cwd()
    current = target.resolve()
    while current != current.parent:
        if (current / ".gitty").is_dir():
            return True
        current = current.parent
    if (current / ".gitty").is_dir():
        return True

    print(bcolors.FAIL + "fatal: not a gitty repository (or any of the parent directories): .gitty" + bcolors.ENDC)
    return False

def main():
    parser = argparse.ArgumentParser(description='Gitty: A Python Git Clone')

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    subparsers.add_parser('init', help='Initialize a new Gitty repository')

    commit_parser = subparsers.add_parser('commit', help='Commit staged changes')
    commit_parser.add_argument('message', type=str, nargs="?", help='The commit message')

    subparsers.add_parser('status', help='shows the diff between the working dir and index')

    index_parser = subparsers.add_parser('add', help="add files to index: 'gitty add .' or 'gitty add <file>'")
    index_parser.add_argument('file', type=str, help="single file or all the files")

    branch_parser = subparsers.add_parser('branch', help="List, create, or delete branches")
    branch_parser.add_argument('branch_name', type=str, nargs="?", default=None, help="Name of the branch to create")
    branch_parser.add_argument("-l", "--list", action='store_true', help="List local branches")
    branch_parser.add_argument("-a", "--all", action='store_true', help="List both local and remote-tracking branches")
    branch_parser.add_argument("-r", "--remotes", action='store_true', help="List remote-tracking branches")
    branch_parser.add_argument("-d", "--delete", type=str, help="Delete a local branch")

    checkout_parser = subparsers.add_parser('checkout', help="checkout to branch")
    checkout_parser.add_argument('branch_name', type=str, help="branch to checkout to")

    subparsers.add_parser('log', help="print the commit history")

    unstage_parser = subparsers.add_parser('restore', help="unstage the file from index")
    unstage_parser.add_argument('file', type=str, help="specify a single file or '.' for all files")

    diff_parser = subparsers.add_parser('diff', help="Show changes between commits, commit and working tree, etc.")
    diff_group = diff_parser.add_mutually_exclusive_group(required=False)
    diff_group.add_argument('--head', action='store_true', dest='head', help="Diff between latest commit and local directory")
    diff_group.add_argument('--cached', action='store_true', help="Diff between index and latest commit")
    diff_group.add_argument('--all', action='store_true', help="Include untracked files marked with intent-to-add")
    diff_group.add_argument('--ours', action='store_true', help="Diff merge-aware (ours)")
    diff_group.add_argument('--theirs', action='store_true', help="Diff merge-aware (theirs)")
    diff_parser.add_argument('files', nargs='*', help="Specific files to diff separated by spaces")

    reset_parser = subparsers.add_parser('reset', help="Reset current HEAD to the specified state")
    reset_group = reset_parser.add_mutually_exclusive_group(required=True)
    reset_group.add_argument("--soft", action="store_true", help="Reset ref only")
    reset_group.add_argument("--mixed", action="store_true", help="Reset ref and index")
    reset_group.add_argument("--hard", action="store_true", help="Reset ref, index, and working tree")
    reset_parser.add_argument("commit", nargs="?", default="HEAD~1", help="The commit to reset to")

    cherry_parser = subparsers.add_parser("cherry-pick", help="Cherry-pick changes from a commit")
    cherry_group = cherry_parser.add_mutually_exclusive_group(required=False)
    cherry_group.add_argument("--no-commit", action='store_true', help="Apply changes without creating a commit")
    cherry_group.add_argument('-e', type=str, help="Add commit message")
    cherry_group.add_argument('-m', type=int, default=0, help="Parent index for cherry-picking merge commit")
    cherry_parser.add_argument("commit_hash", type=str, help="Commit hash to cherry-pick")

    merge_parser = subparsers.add_parser('merge', help="Merge a branch into the active branch")
    merge_group = merge_parser.add_mutually_exclusive_group(required=True)
    merge_group.add_argument('--abort', action='store_true', help="Abort current merge and restore HEAD")
    merge_group.add_argument('target_ref', nargs='?', help="Branch or remote tracking ref to merge")

    config_parser = subparsers.add_parser('config', help="Set repository configuration")
    config_parser.add_argument('--global', dest='is_global', action='store_true', help="Store values in global config")
    config_group = config_parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument('--user_name', type=str, help="Set user name")
    config_group.add_argument('--user_email', type=str, help="Set user email")

    push_parser = subparsers.add_parser('push', help="Push commits to remote")
    push_parser.add_argument('remote', type=str, nargs="?", default=None, help="Remote name (e.g. origin)")
    push_parser.add_argument('branch', type=str, nargs="?", default=None, help="Branch name")
    push_parser.add_argument('-u', '--set-upstream', action='store_true', help="Set upstream tracking branch")

    fetch_parser = subparsers.add_parser('fetch', help="Download objects and tracking refs from remote")
    fetch_parser.add_argument('remote', nargs='?', default='origin', help="Remote name (default: origin)")

    pull_parser = subparsers.add_parser('pull', help="Fetch from and integrate with another repository or branch")
    pull_parser.add_argument('remote', nargs='?', default='origin', help="Remote name (default: origin)")
    pull_parser.add_argument('branch', nargs='?', default=None, help="Branch name to pull")

    # Remote subparser
    remote_parser = subparsers.add_parser('remote', help="Manage set of tracked repositories")
    remote_parser.add_argument('-v', '--verbose', action='store_true', help="Be verbose; must be placed after remote")
    remote_subparsers = remote_parser.add_subparsers(dest="remote_action")

    remote_default_head_parset = remote_subparsers.add_parser("default-head" , help="Change the deafult head in remote")
    remote_default_head_parset.add_argument("branch", type=str, help="change default head to specified branch")

    # gitty remote add <name> <url>
    remote_add_parser = remote_subparsers.add_parser('add', help="Add a remote repository")
    remote_add_parser.add_argument('name', type=str, help="Name of the remote (e.g. origin)")
    remote_add_parser.add_argument('url', type=str, help="Remote namespace/repo (e.g. dhanush/demo-repo)")

    # gitty remote remove <name>
    remote_rm_parser = remote_subparsers.add_parser('remove', help="Remove a remote repository")
    remote_rm_parser.add_argument('name', type=str, help="Name of the remote to remove")

    clone_parser = subparsers.add_parser('clone', help="clone repository")
    clone_parser.add_argument("url", type=str, help="enter the url eg:clone dhanush/demo-repo")

    args = parser.parse_args()

    if args.command not in EXEMPT_COMMANDS:
            if not check_gitty_repo():
                sys.exit(1)
                
    repo = Repository()
    index = Index()
    hub = Gitty_hub()

    if args.command == 'init':
        try:
            print("Initializing Gitty repository...")
            repo.initilization()
            print("Gitty repository initializes")
        except Exception as e:
            print(bcolors.RED + e + bcolors.ENDC)
    elif args.command == "config":
        if args.user_name:
            section, key, value = 'user', 'name', args.user_name
        else:
            section, key, value = 'user', 'email', args.user_email
        repo.set_config_value(key, value, section, is_global=args.is_global)

    elif args.command == 'commit':
        repo.commit(args.message)

    elif args.command == "status":
        index.status()

    elif args.command == "add":
        if args.file == ".":
            index.add_all()
        else:
            index.index_add(args.file)
        print("files are stages")

    elif args.command == "restore":
        if temp_index_exist():
            repo.unstage_merge(args.file)
        else:
            index.unstage_file(args.file)

    elif args.command == 'branch':
        # Delete branch
        if args.delete:
            repo.delete_branch(args.delete)

        elif args.branch_name == "?":
            print(f"Current on branch '{get_current_branch()}'")
            return
        elif args.branch_name and not (args.list or args.all or args.remotes):
            repo.create_branch(args.branch_name)

        # List branches (triggered by 'gitty branch', '--list', '-a', or '-r')
        else:
            repo.list_branches(show_all=args.all, show_remotes=args.remotes)
                
    elif args.command == "checkout":
        repo.branch_checkout(args.branch_name)

    elif args.command == "log":
        repo.log()

    elif args.command == "diff":
        if args.head:
            repo.diff("head")
        elif args.cached:
            repo.diff("cached")
        elif args.all:
            repo.diff_intent_to_add()
        elif args.ours or args.theirs:
            side = 'ours' if args.ours else 'theirs'
            repo.diff_merge_aware(args.files if args.files else None, side)
        elif args.files:
            repo.diff_files(args.files)
        else:
            repo.diff(None)

    elif args.command == "reset":
        if not args.commit.split('~')[-1].isnumeric():
            print('Invalid value for commit history')
            return
        if args.soft:
            repo.soft_reset(args.commit)
        elif args.mixed:
            repo.mixed_rest(args.commit)
        elif args.hard:
            repo.hard_reset(args.commit)

    elif args.command == "cherry-pick":
        repo.cherry_pick(args.commit_hash, args.no_commit, args.e, args.m)

    elif args.command == "merge":
        if args.target_ref:
            repo.merge(args.target_ref)
        elif args.abort:
            repo.merge_abort()

    elif args.command == "push":
        asyncio.run(hub.push(remote_name=args.remote, branch_name=args.branch))
    elif args.command == "fetch":
        asyncio.run(hub.fetch())

    elif args.command == "pull":
        asyncio.run(hub.pull(remote_name=args.remote, branch_name=args.branch))

    elif args.command == "remote":
        if args.remote_action == 'add':
            repo.remote_add(args.name, args.url)
        elif args.remote_action == "default-head":
            asyncio.run(hub.set_default_branch(args.branch))
        elif args.remote_action == 'remove':
            repo.remote_remove(args.name)
        else:
            # Default behavior: 'gitty remote' or 'gitty remote -v'
            repo.remote_list(verbose=args.verbose)

    elif args.command == "clone":
        asyncio.run(hub.clone_repo(args.url))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()