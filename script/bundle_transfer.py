import base64
import binascii
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def require_clean():
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Working tree must be clean, including untracked files.")


def require_branch(branch):
    if branch == "main":
        raise ValueError("Refusing to export or import main; use a feature branch.")
    subprocess.run(["git", "check-ref-format", "--branch", branch], check=True, capture_output=True)


def prepare(branch=None, base="main"):
    require_clean()
    branch = branch or git("symbolic-ref", "--short", "HEAD")
    require_branch(branch)
    head = git("rev-parse", "--verify", f"refs/heads/{branch}")
    base_sha = git("rev-parse", "--verify", f"{base}^{{commit}}")
    if branch == base or head == base_sha:
        raise ValueError("Branch has no exclusive commits.")
    if not git("rev-list", f"{base_sha}..{head}"):
        raise ValueError("Branch has no exclusive commits.")
    root = Path(git("rev-parse", "--show-toplevel"))
    if (root / "bundle.bundle").exists() or list(root.glob("bundle.b64*")):
        raise ValueError("Move previous bundle.bundle and bundle.b64* aside before exporting again.")
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory) / "bundle.bundle"
        subprocess.run(["git", "bundle", "create", str(bundle), f"{base_sha}..refs/heads/{branch}"], check=True)
        subprocess.run(["git", "bundle", "verify", str(bundle)], check=True)
        data = bundle.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        lines = [encoded[index : index + 76] for index in range(0, len(encoded), 76)]
        chunks = [lines[index : index + 1000] for index in range(0, len(lines), 1000)]
        with (root / "bundle.bundle").open("xb") as output:
            output.write(data)
        for index, chunk in enumerate(chunks, 1):
            name = "bundle.b64" if len(chunks) == 1 else f"bundle.b64.{index}"
            with (root / name).open("x", encoding="ascii") as output:
                output.write("\n".join(chunk) + "\n")
    print(f"Prepared {branch} against {base} ({base_sha}); {len(chunks)} chunk(s) in {root}.")
    print(f"Target: bash script/unpack-bundle.sh {branch}")
    print(f"User publishes: git push -u origin {branch}")
    print("User opens PR: gh pr create")


def transfer_data(directory):
    single = directory / "bundle.b64"
    numbered = list(directory.glob("bundle.b64.*"))
    if single.exists() and numbered:
        raise ValueError("Ambiguous transfer: both single and numbered Base64 files exist.")
    if single.exists():
        encoded = single.read_bytes()
    elif numbered:
        chunks = {}
        for path in numbered:
            match = re.fullmatch(r"bundle\.b64\.([1-9][0-9]*)", path.name)
            if not match:
                raise ValueError(f"Invalid chunk name: {path.name}")
            chunks[int(match[1])] = path
        if sorted(chunks) != list(range(1, len(chunks) + 1)):
            raise ValueError("Missing numbered chunks; expected contiguous chunks starting at 1.")
        encoded = b"".join(chunks[index].read_bytes() for index in sorted(chunks))
    else:
        return (directory / "bundle.bundle").read_bytes()
    try:
        return base64.b64decode(b"".join(encoded.split()), validate=True)
    except binascii.Error as error:
        raise ValueError("Invalid Base64 transfer.") from error


def unpack(branch=None, directory="."):
    require_clean()
    data = transfer_data(Path(directory).resolve())
    with tempfile.TemporaryDirectory() as temporary:
        bundle = Path(temporary) / "bundle.bundle"
        bundle.write_bytes(data)
        subprocess.run(["git", "bundle", "verify", str(bundle)], check=True)
        heads = [line.split(" ", 1)[1] for line in git("bundle", "list-heads", str(bundle)).splitlines()]
        if len(heads) != 1 or not heads[0].startswith("refs/heads/"):
            raise ValueError("Expected exactly one feature branch in the bundle.")
        detected = heads[0].removeprefix("refs/heads/")
        if branch is not None and branch != detected:
            raise ValueError(f"Requested branch does not match bundle branch {detected}.")
        branch = detected
        require_branch(branch)
        subprocess.run(["git", "fetch", "--no-tags", str(bundle), heads[0]], check=True)
        incoming = git("rev-parse", "FETCH_HEAD")
        exists = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"])
        if exists.returncode == 0:
            ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", f"refs/heads/{branch}", incoming])
            if ancestor.returncode != 0:
                raise ValueError("Local branch is ahead or divergent; merge/rebase manually before importing.")
            subprocess.run(["git", "switch", branch], check=True)
            subprocess.run(["git", "merge", "--ff-only", incoming], check=True)
        elif exists.returncode == 1:
            subprocess.run(["git", "switch", "-c", branch, incoming], check=True)
        else:
            raise ValueError("Could not inspect local branch.")
    print(f"Imported {branch} at {incoming}; no remote was modified.")


def main():
    try:
        action, *args = sys.argv[1:]
        if len(args) > 2 or action not in {"prepare", "unpack"}:
            raise ValueError("Usage: bundle_transfer.py prepare|unpack [branch] [base|directory]")
        {"prepare": prepare, "unpack": unpack}[action](*args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
