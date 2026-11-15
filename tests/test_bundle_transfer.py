import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "script"


def run(cwd, *args, check=True):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Bundle Test",
        "GIT_AUTHOR_EMAIL": "bundle@example.invalid",
        "GIT_COMMITTER_NAME": "Bundle Test",
        "GIT_COMMITTER_EMAIL": "bundle@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True, check=check)


def git(cwd, *args):
    return run(cwd, "git", *args).stdout.strip()


@pytest.fixture
def repositories(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    git(source, "init", "-b", "main")
    (source / ".gitignore").write_text("bundle.bundle\nbundle.b64*\n")
    git(source, "add", ".gitignore")
    git(source, "commit", "-m", "base")
    git(tmp_path, "clone", str(source), str(target))
    git(source, "switch", "-c", "feat/transfer")
    (source / "payload.txt").write_text("first payload\n")
    git(source, "add", "payload.txt")
    git(source, "commit", "-m", "feature")
    return source, target


def prepare(source):
    run(source, "bash", str(SCRIPT / "prepare-bundle.sh"))
    return (source / "bundle.b64").read_bytes()


def unpack(target, check=True):
    return run(target, "bash", str(SCRIPT / "unpack-bundle.sh"), check=check)


def test_round_trip_and_existing_checked_out_branch(repositories):
    source, target = repositories
    (target / "bundle.b64").write_bytes(prepare(source))
    unpack(target)
    assert git(target, "branch", "--show-current") == "feat/transfer"
    assert git(target, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    unpack(target)
    assert (target / "payload.txt").read_text() == "first payload\n"


def test_numbered_chunks_are_numeric_and_override_stale_bundle(repositories):
    source, target = repositories
    encoded = prepare(source)
    (target / "bundle.bundle").write_bytes(b"stale invalid bundle")
    chunks = [encoded[index : index + 16] for index in range(0, len(encoded), 16)]
    assert len(chunks) > 10
    for index, chunk in enumerate(chunks, 1):
        (target / f"bundle.b64.{index}").write_bytes(chunk)
    unpack(target)
    assert git(target, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    assert (target / "bundle.bundle").read_bytes() == b"stale invalid bundle"


@pytest.mark.parametrize("dirty", ["payload.txt", "untracked.txt"])
def test_prepare_refuses_dirty_tree(repositories, dirty):
    source, _ = repositories
    (source / dirty).write_text("uncommitted\n")
    result = run(source, "bash", str(SCRIPT / "prepare-bundle.sh"), check=False)
    assert result.returncode != 0
    assert not (source / "bundle.bundle").exists()


def test_prepare_does_not_overwrite_previous_transfer(repositories):
    source, _ = repositories
    encoded = prepare(source)
    result = run(source, "bash", str(SCRIPT / "prepare-bundle.sh"), check=False)
    assert result.returncode != 0
    assert (source / "bundle.b64").read_bytes() == encoded


@pytest.mark.parametrize("mode", ["invalid", "missing", "ambiguous", "corrupt-bundle"])
def test_invalid_transfer_does_not_move_head(repositories, mode):
    source, target = repositories
    encoded = prepare(source)
    before = git(target, "rev-parse", "HEAD")
    if mode == "invalid":
        (target / "bundle.b64").write_bytes(b"not base64!")
    elif mode == "missing":
        (target / "bundle.b64.2").write_bytes(encoded)
    elif mode == "ambiguous":
        (target / "bundle.b64").write_bytes(encoded)
        (target / "bundle.b64.1").write_bytes(encoded)
    else:
        (target / "bundle.bundle").write_bytes(b"invalid bundle")
    assert unpack(target, check=False).returncode != 0
    assert git(target, "rev-parse", "HEAD") == before


def test_unpack_refuses_dirty_tree(repositories):
    source, target = repositories
    (target / "bundle.b64").write_bytes(prepare(source))
    (target / "untracked.txt").write_text("keep me")
    assert unpack(target, check=False).returncode != 0
    assert git(target, "branch", "--show-current") == "main"
    assert (target / "untracked.txt").read_text() == "keep me"


def test_unpack_refuses_divergent_branch(repositories):
    source, target = repositories
    (target / "bundle.b64").write_bytes(prepare(source))
    git(target, "switch", "-c", "feat/transfer")
    (target / "local.txt").write_text("local work")
    git(target, "add", "local.txt")
    git(target, "commit", "-m", "local change")
    before = git(target, "rev-parse", "HEAD")
    assert unpack(target, check=False).returncode != 0
    assert git(target, "rev-parse", "HEAD") == before


def test_existing_branch_fast_forwards_from_new_transfer(repositories, tmp_path):
    source, target = repositories
    (target / "bundle.b64").write_bytes(prepare(source))
    unpack(target)
    (source / "payload.txt").write_text("second payload\n")
    git(source, "add", "payload.txt")
    git(source, "commit", "-m", "second feature commit")
    archived = tmp_path / "archive"
    archived.mkdir()
    for name in ("bundle.bundle", "bundle.b64"):
        (source / name).rename(archived / name)
    (target / "bundle.b64").write_bytes(prepare(source))
    unpack(target)
    assert git(target, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    assert (target / "payload.txt").read_text() == "second payload\n"


def test_large_export_splits_at_1000_lines(repositories):
    source, target = repositories
    (source / "random.bin").write_bytes(os.urandom(90000))
    git(source, "add", "random.bin")
    git(source, "commit", "-m", "large payload")
    run(source, "bash", str(SCRIPT / "prepare-bundle.sh"))
    assert not (source / "bundle.b64").exists()
    chunks = list(source.glob("bundle.b64.*"))
    assert len(chunks) > 1
    for chunk in chunks:
        lines = chunk.read_bytes().splitlines()
        assert len(lines) <= 1000
        assert all(len(line) <= 76 for line in lines)
        (target / chunk.name).write_bytes(chunk.read_bytes())
    unpack(target)
    assert (target / "random.bin").read_bytes() == (source / "random.bin").read_bytes()


def test_prepare_refuses_main(repositories):
    source, _ = repositories
    git(source, "switch", "main")
    result = run(source, "bash", str(SCRIPT / "prepare-bundle.sh"), check=False)
    assert result.returncode != 0
    assert not (source / "bundle.bundle").exists()


def test_unpack_refuses_missing_base(repositories, tmp_path):
    source, _ = repositories
    encoded = prepare(source)
    empty = tmp_path / "empty"
    empty.mkdir()
    git(empty, "init", "-b", "main")
    (empty / ".gitignore").write_text("bundle.*\n")
    git(empty, "add", ".gitignore")
    git(empty, "commit", "-m", "unrelated base")
    (empty / "bundle.b64").write_bytes(encoded)
    before = git(empty, "rev-parse", "HEAD")
    assert unpack(empty, check=False).returncode != 0
    assert git(empty, "rev-parse", "HEAD") == before
