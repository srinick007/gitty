import asyncio
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path

import httpx
import requests

from gitty.backend_utils import check_missing, commit_full_walk, commit_full_walk_just_hashes, get_hashes, ref_saver
from gitty.colors import bcolors
from gitty.utils import  get_config_value, get_current_branch, get_local_refs, get_upstream, set_config_value, set_upstream
from gitty.repository import Repository
from gitty.git_objects import Commit, Git_objects, Tree

@contextmanager
def working_directory(path: Path):
    prev_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)


class Gitty_hub:
    repo = Repository()

    @property
    def repo_path(self) -> Path:
        return Path.cwd().resolve()

    @property
    def BACKEND_ENDPOINT(self) -> Path:
        return 'https://gitty-backend-vc9v.onrender.com'

    @property
    def BLOB_PATH(self) -> Path:
        return self.repo_path / '.gitty' / 'objects'

    @property
    def config_path(self) -> Path:
        return self.repo_path / '.gitty' / 'config'

    async def send_blob(self, object_hash: str, object_type: str, client: httpx.AsyncClient):
        folder_name, file_name = object_hash[:2], object_hash[2:]
        file_path = self.BLOB_PATH / folder_name / file_name

        try:
            # Read bytes directly to avoid unclosed file handles
            file_bytes = file_path.read_bytes()
            files = {'file': (file_name, file_bytes, 'application/octet-stream')}
            payload = {
                'metadata': json.dumps({
                    'hash': object_hash,
                    'type': object_type,
                })
            }
            response = await client.post(f"{self.BACKEND_ENDPOINT}/uploadfile/", files=files, data=payload)
            response.raise_for_status()
        except Exception as e:
            print(f"Upload failed for {object_hash}: {e}")

    async def get_blob(self, object_hash: str, client: httpx.AsyncClient):
        try:
            response = await client.get(f"{self.BACKEND_ENDPOINT}/blob/{object_hash}")
            data = json.loads(response.content)
            decoded = base64.b64decode(data['data']['$binary'])
            return (object_hash, decoded)
        except Exception as e:
            print(f"Failed fetching blob {object_hash}: {e}")
            return (object_hash, None)

    async def push_all_objects(self, all_hashes: dict):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        async with httpx.AsyncClient(limits=limits, timeout=None) as client:
            tasks = [self.send_blob(obj_hash, meta['type'], client) for obj_hash, meta in all_hashes.items()]
            results = await asyncio.gather(*tasks)
            print(f"Uploaded {len(results)} objects.")

    async def push(self, remote_name: str = "origin", branch_name: str = None, set_upstream_flag: bool = False, force: bool = False):
        try:
            
            author = get_config_value(self.repo_path, 'user', 'name', default=None)
            if not author:
                print(bcolors.RED + "fatal: Set user.name before pushing to hub." + bcolors.ENDC)
                return

            current_branch = get_current_branch()
            target_branch = branch_name if branch_name else current_branch

            if not remote_name or not branch_name:
                upstream_remote, upstream_branch = get_upstream(current_branch, self.repo_path)
                remote_name = remote_name or upstream_remote
                branch_name = branch_name or upstream_branch or current_branch

            if not remote_name:
                print(f"fatal: The current branch '{current_branch}' has no upstream branch.")
                print(f"To push and set remote tracking, use:")
                print(f"    gitty push -u origin {current_branch}")
                return

            # Save upstream if -u was passed
            if set_upstream_flag:
                set_upstream(current_branch, remote_name, branch_name, self.repo_path)
                print(f"Branch '{current_branch}' set up to track remote branch '{branch_name}' from '{remote_name}'.")

            target_branch_file = Path(self.repo_path) / '.gitty' / 'refs' / 'heads' / target_branch
            if not target_branch_file.exists():
                print(bcolors.RED + f"fatal: Branch '{target_branch}' does not exist locally." + bcolors.ENDC)
                return

            commit_hash = target_branch_file.read_text().strip()
            remote_url = get_config_value(self.repo_path, f'remote "{remote_name}"', 'url', default=None)

            # --- CASE 1: INITIAL REPOSITORY CREATION ---
            if remote_url is None:
                repo_name = input("Enter remote repository name: ").strip()
                payload = {
                    'repo_name': repo_name,
                    'author': author,
                    'commit_hash': commit_hash,
                    'current_branch': target_branch
                }

                all_hashes = get_hashes(commit_hash)
                response = requests.post(f"{self.BACKEND_ENDPOINT}/init/", json=payload)
                response.raise_for_status()

                data = response.json()
                if data.get('status') == 'success':
                    full_url = f"{author}/{repo_name}"
                    set_config_value(
                        key='url',
                        value=full_url,
                        section=f'remote "{remote_name}"',
                        repo_path=self.repo_path
                    )
                    
                    await self.push_all_objects(all_hashes)
                    self._update_remote_ref(remote_name, target_branch, commit_hash)
                    print(bcolors.GREEN + f"Repository created and pushed to {full_url}" + bcolors.ENDC)
                    return

                elif data.get('status') == 'failure':
                    print(bcolors.RED + f"Error: {data.get('msg')}" + bcolors.ENDC)
                    return

            # --- CASE 2: INCREMENTAL PUSH ---
            print(f"Pushing to {remote_name} ({remote_url})...")
            remote_author, repo_name = remote_url.split("/")

            # Check remote branch state
            branch_check_url = f"{self.BACKEND_ENDPOINT}/author/{remote_author}/repo/{repo_name}/branch/{target_branch}"
            response = requests.get(branch_check_url)

            if response.status_code == 200:
                remote_latest_hash = response.json().get('latest_hash')
                if commit_hash == remote_latest_hash and not force:
                    print(bcolors.GREEN + "Everything up-to-date." + bcolors.ENDC)
                    return

            # STEP 1: Traverse local DAG
            all_hashes = get_hashes(commit_hash)

            # STEP 2: Negotiate missing objects
            check_payload = {"hashes": list(all_hashes.keys())}
            check_response = requests.post(f"{self.BACKEND_ENDPOINT}/repo/check-missing", json=check_payload)
            check_response.raise_for_status()
            missing_hashes = check_response.json().get('missing_hashes', [])

            # STEP 3: Upload missing objects
            if missing_hashes:
                hashes_to_send = {h: all_hashes[h] for h in missing_hashes if h in all_hashes}
                print(f"Uploading {len(hashes_to_send)} object(s)...")
                await self.push_all_objects(hashes_to_send)
            else:
                print("No new objects to upload.")

            # STEP 4: Update remote branch reference
            payload = {
                "author": remote_author,
                "repo_name": repo_name,
                "branch_name": target_branch,
                "branch_hash": commit_hash,
                "force": force
            }
            branch_response = requests.post(f"{self.BACKEND_ENDPOINT}/repo/update-branch", json=payload)

            if not branch_response.ok:
                try:
                    err_msg = branch_response.json().get("detail", branch_response.text)
                except Exception:
                    err_msg = branch_response.text
                print(bcolors.RED + f"\n{err_msg}" + bcolors.ENDC)
                return

            # STEP 5: Update local tracking reference
            self._update_remote_ref(remote_name, target_branch, commit_hash)

            if set_upstream:
                set_config_value(key='remote', value=remote_name, section=f'branch "{target_branch}"', repo_path=self.repo_path)
                set_config_value(key='merge', value=f'refs/heads/{target_branch}', section=f'branch "{target_branch}"', repo_path=self.repo_path)
                print(f"Branch '{target_branch}' set up to track remote branch '{target_branch}' from '{remote_name}'.")

            print(bcolors.GREEN + f"Push successful: {target_branch} -> {remote_name}/{target_branch} ({commit_hash[:7]})" + bcolors.ENDC)

        except requests.exceptions.RequestException as req_err:
            print(bcolors.RED + f"\n[Network Error] Push failed: {req_err}" + bcolors.ENDC)
        except Exception as e:
            print(bcolors.RED + f"\n[Push Error] {e}" + bcolors.ENDC)

    def _update_remote_ref(self, remote_name: str, branch_name: str, commit_hash: str):
        """Syncs .gitty/refs/remotes/<remote>/<branch> after push."""
        ref_dir = Path(self.repo_path) / '.gitty' / 'refs' / 'remotes' / remote_name
        ref_dir.mkdir(parents=True, exist_ok=True)
        (ref_dir / branch_name).write_text(f"{commit_hash.strip()}\n")

    async def get_remote_refs(self, remote_name:str = "origin"):
        remote = get_config_value(self.repo_path, f'remote "{remote_name}"', 'url', default=None)
        if not remote:
            return {}
        author, repo_name = remote.split("/")
        payload = {"repo_path": remote}
        response = requests.get(f"{self.BACKEND_ENDPOINT}/repo-refs/{author}/{repo_name}", json=payload)
        data = json.loads(response.content)
        if data.get("status") == "success":
            return data.get("refs", {})
        return {}

    async def get_missing_blobs(self, missing: dict):
        missing_hashes = check_missing(missing)
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

        async with httpx.AsyncClient(limits=limits, timeout=None) as client:
            tasks = [self.get_blob(h, client) for h in missing_hashes]
            results = await asyncio.gather(*tasks)

        for obj_hash, binary in results:
            if binary:
                Git_objects.save_from_remote_compressed(obj_hash, binary)


    async def fetch(self, remote_name: str = "origin"):

        local_refs = get_local_refs(self.repo_path)  
        remote_refs = await self.get_remote_refs(remote_name)  
        
        if not remote_refs:
            print(f"No refs found on remote '{remote_name}'.")
            return

        remote_ref_dir = self.repo_path / '.gitty' / 'refs' / 'remotes' / remote_name
        remote_ref_dir.mkdir(parents=True, exist_ok=True)

        # Fetch missing objects for all remote refs
        missing_wants = {}
        for ref, remote_commit in remote_refs.items():
            folder, file_name = remote_commit[:2], remote_commit[2:]
            remote_blob_file = Git_objects.objects_path / folder / file_name
            if not remote_blob_file.exists():
                missing_wants[ref] = remote_commit

        if missing_wants:
            payload = {
                "want": missing_wants,
                "have": local_refs
            }
            response = requests.post(f"{self.BACKEND_ENDPOINT}/get-remote-ref", json=payload)
            response.raise_for_status()
            data = response.json()
            await self.get_missing_blobs(data["data"])

        # Update remote-tracking refs and report sync status
        for ref, remote_commit in remote_refs.items():
            remote_ref_file = remote_ref_dir / ref
            remote_ref_file.write_text(remote_commit.strip() + "\n")
            print(f"Updated remote tracking ref {remote_name}/{ref} -> {remote_commit[:7]}")

            local_commit = local_refs.get(ref)
            if not local_commit:
                print(f" * [new branch] {ref} -> {remote_name}/{ref}")
                continue

            if local_commit == remote_commit:
                print(f"Branch '{ref}' is up to date.")
            elif Commit.DFS(local_commit, target_hash=remote_commit):
                print(f"Local branch '{ref}' is ahead of {remote_name}/{ref} (Unpushed local commits).")
            elif Commit.DFS(remote_commit, target_hash=local_commit):
                print(f"Remote branch '{ref}' is ahead of local (Fast-forward available).")
            else:
                print(f"Branch '{ref}' and {remote_name}/{ref} have diverged (Merge required).")

    async def pull(self, remote_name: str = None, branch_name: str = None):

        
        current_branch = get_current_branch()

        # 1. Resolve remote and branch from upstream if omitted
        if not remote_name or not branch_name:
            upstream_remote, upstream_branch = get_upstream(current_branch, self.repo_path)
            remote_name = remote_name or upstream_remote or "origin"
            branch_name = branch_name or upstream_branch or current_branch

        if not remote_name or not branch_name:
            print(f"fatal: No upstream configured for branch '{current_branch}'.")
            print(f"Usage: gitty pull <remote> <branch>")
            return

        # 2. Fetch updates into refs/remotes/<remote>/
        print(f"Fetching from {remote_name}...")
        await self.fetch(remote_name=remote_name)

        # 3. Merge remote-tracking ref into current active branch
        tracking_ref = f"{remote_name}/{branch_name}"
        print(f"Merging {tracking_ref} into {current_branch}...")
        self.repo.merge(branch_name=tracking_ref, base_branch=current_branch)

    async def set_default_branch(self,branch_name):
        branch_path = Path(self.repo_path / 'refs' / 'heads' / branch_name)
        if not branch_path.exists():
            print(bcolors.RED + f"branch {branch_name} does not exist" + bcolors.ENDC)
            return
        
        remote_url = get_config_value(self.repo_path, 'remote "origin"', 'url', default=None)
        payload = {"url" : remote_url,
                   "new_head": branch_name}
        response = requests.post(f"{self.BACKEND_ENDPOINT}/repo/set-default-branch" , json = payload)
        # print(response)
        data = json.loads(response.content)
        print(data["status"], f"default head has been changed to {branch_name}")

        return
            
    async def clone_repo(self, url: str):
        if "/" not in url:
            print(bcolors.FAIL + f"fatal: Invalid repository format '{url}'. Expected 'author/repo_name'" + bcolors.ENDC)
            return

        author, repo_name = url.split("/")
        repo_path = Path.cwd() / repo_name
        
        if repo_path.exists():
            print(bcolors.FAIL + f"fatal: destination path '{repo_name}' already exists." + bcolors.ENDC)
            return
        
        repo_path.mkdir(parents=True)

        with working_directory(repo_path):
            repo = Repository()
            repo.initilization()
            
            # Fetch remote references manifest
            repo_refs = requests.get(f"{self.BACKEND_ENDPOINT}/repo-refs/{author}/{repo_name}")
            if not repo_refs.ok:
                print(bcolors.FAIL + f"fatal: Repository '{author}/{repo_name}' not found on remote." + bcolors.ENDC)
                return

            repo_data = repo_refs.json()
            default_branch = repo_data.get("head", "main")
            refs_map = repo_data.get("refs", {})

            if not refs_map:
                print(bcolors.WARNING + "warning: You appear to have cloned an empty repository." + bcolors.ENDC)
                repo.remote_add("origin", url)
                return

            # Add remote origin config
            repo.remote_add("origin", url)

            # Request object graph manifest from server
            payload = {
                "want": refs_map,
                "have": {}
            }
            response = requests.post(f"{self.BACKEND_ENDPOINT}/get-remote-ref", json=payload)
            response.raise_for_status()
            object_data = response.json()

            # Download and decompress all missing blobs/trees/commits into .gitty/objects
            await self.get_missing_blobs(object_data["data"])

            # Save ALL branches to remote-tracking directory (remotes/origin/*)
            for ref, commit_hash in refs_map.items():
                ref_saver(repo_path, "remotes/origin", ref, commit_hash)

            # Save only the default branch to local heads
            default_commit_hash = refs_map.get(default_branch)
            if default_commit_hash:
                ref_saver(repo_path, "heads", default_branch, default_commit_hash)

            
            # Set upstream for the default branch
            set_upstream(default_branch, remote_name="origin", remote_branch=default_branch, repo_path=repo_path)

            # Set symbolic HEAD to point to default branch
            (repo_path / '.gitty' / 'HEAD').write_text(f"ref: refs/heads/{default_branch}\n")

            # sUnpack files into workspace
            repo.workspace_change()
            print(bcolors.GREEN + f"Successfully cloned into '{repo_name}'." + bcolors.ENDC)

                