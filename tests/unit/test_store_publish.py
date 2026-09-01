"""PublishPolicy: who is allowed to push a store's memory, and why.

The case that matters is a worktree store, which shares the host repo's
remote — so an unqualified push publishes memory wherever the project
publishes its code.
"""

import subprocess

from redthread.store import LocalStore, PublishPolicy, gitio


def _host_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    gitio.configure_identity(path, "Test", "test@example.com")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def test_store_without_a_remote_is_allowed_to_publish(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])

    policy = store.publish_policy()

    assert policy.allowed is True
    assert policy.remote_url is None


def test_store_with_its_own_remote_publishes_by_default(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    gitio.set_remote(store.layout.root, str(_bare_remote(tmp_path)))

    policy = store.publish_policy()

    assert policy.allowed is True
    assert policy.inherited_remote is False


def test_worktree_store_does_not_publish_to_the_host_repos_remote(tmp_path):
    host = _host_repo(tmp_path / "host")
    gitio.set_remote(host, str(_bare_remote(tmp_path)))
    store = LocalStore.init_worktree(
        host, tmp_path / "store-wt", "memories", project_id="demo", phases=["build"]
    )

    policy = store.publish_policy()

    assert policy.allowed is False
    assert policy.inherited_remote is True
    assert "worktree" in policy.reason


def test_explicit_publish_setting_overrides_the_worktree_default(tmp_path):
    host = _host_repo(tmp_path / "host")
    gitio.set_remote(host, str(_bare_remote(tmp_path)))
    store = LocalStore.init_worktree(
        host, tmp_path / "store-wt", "memories", project_id="demo", phases=["build"]
    )

    store.set_publish(True)

    assert store.publish_policy().allowed is True
    # and it survives a reopen, because it lives in project.yaml
    assert LocalStore(store.layout.root).publish_policy().allowed is True


def test_publish_false_stops_a_store_that_would_otherwise_publish(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    gitio.set_remote(store.layout.root, str(_bare_remote(tmp_path)))

    store.set_publish(False)

    policy = store.publish_policy()
    assert policy.allowed is False
    assert "publish: false" in policy.reason


def test_resolve_reports_the_remote_it_would_push_to(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    remote = _bare_remote(tmp_path)
    gitio.set_remote(store.layout.root, str(remote))

    policy = PublishPolicy.resolve(store.layout.root, declared=None)

    assert policy.remote_url == str(remote)
