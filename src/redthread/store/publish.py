"""Whether a store's memory may be pushed to its git remote, and why.

Committing and pushing are separate concerns: a commit makes memory durable
and has no consequences beyond the machine it happens on, while a push
publishes it. This module decides only the second, so that every caller can
commit unconditionally.

The case that forces the distinction is a worktree store. `redthread init
--worktree-repo` presents the store as separate from the project — its own
orphan branch, gitignored in the host repo — but a worktree shares the host
repo's remotes, so an unqualified "push" sends memory wherever the project
publishes its code, which may be a public repository. That is never a safe
default, so a worktree store publishes only when the project says so.
"""

from dataclasses import dataclass
from pathlib import Path

from redthread.store import gitio

ENABLE_HINT = "`redthread publish --enable --store <store>` turns publishing on"


@dataclass(frozen=True)
class PublishPolicy:
    """The publish decision for one store, with the reason it was made."""

    allowed: bool
    remote_url: str | None
    reason: str
    inherited_remote: bool = False

    @classmethod
    def resolve(cls, root: Path, declared: bool | None) -> "PublishPolicy":
        """Decide for the store at `root`, given its manifest's `publish`
        field (None when the project has not said either way).

        Args:
            root: The store directory (a git work tree).
            declared: The project manifest's explicit choice, or None.

        Returns:
            The policy, whose `reason` is written to be shown to a user.
        """
        root = Path(root)
        if not gitio.has_remote(root):
            return cls(
                allowed=True,
                remote_url=None,
                reason="the store has no remote, so nothing can leave this machine",
            )
        url = gitio.get_remote_url(root)
        inherited = gitio.is_worktree(root)
        if declared is True:
            return cls(
                allowed=True,
                remote_url=url,
                reason=f"publishing is enabled for this store (remote: {url})",
                inherited_remote=inherited,
            )
        if declared is False:
            return cls(
                allowed=False,
                remote_url=url,
                reason=f"publishing is disabled for this store (project.yaml sets "
                f"publish: false); {ENABLE_HINT}",
                inherited_remote=inherited,
            )
        if inherited:
            return cls(
                allowed=False,
                remote_url=url,
                reason=f"this store is a worktree of its host repo and shares that repo's "
                f"remote ({url}), so pushing would publish memory wherever this project "
                f"publishes its code — memory stays committed locally until you say "
                f"otherwise; {ENABLE_HINT}",
                inherited_remote=True,
            )
        return cls(
            allowed=True,
            remote_url=url,
            reason=f"the store repo has its own remote ({url})",
        )
