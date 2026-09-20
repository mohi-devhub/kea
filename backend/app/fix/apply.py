"""The only place a real repository may ever be changed. Reserved and DISABLED in this build.

Approval today records who approved which exact diff hash (`ApprovalRecord`) and stops there. This
module is where the post-approval actions will live once they are switched on. It is deliberately
tiny so the approval gate stays easy to audit: anything that mutates git or opens a PR must take an
`ApprovedToken`, and no other module may import git-write helpers.

Planned expansion (docs/FIX_FLOW_SPEC.md sections 10-11):
  1. create a branch `kea/fix-<incident>-<deployment>` from the recorded base commit
  2. `git apply --check`, then apply the exact approved diff, after re-hashing it
  3. commit with `Approved-by` and `Proposed-by` trailers
  4. draft a PR: a local file adapter first, then a GitHub draft-PR adapter (token from env only)
"""

from dataclasses import dataclass


class ApplyNotEnabled(RuntimeError):
    """Raised by every apply entry point in the propose-only build."""


@dataclass(frozen=True)
class ApprovedToken:
    """Proof that a human approved exactly this diff. Only the service can mint one."""

    proposal_id: str
    diff_hash: str
    approver: str


def apply_approved(token: ApprovedToken) -> None:
    raise ApplyNotEnabled(
        f"apply is not enabled in this build (proposal {token.proposal_id}); "
        "the approval was recorded but no repository was changed"
    )
