#!/usr/bin/env bash
# Opens a pull request to the mixing-console-skills repo with the changes made to this skill folder,
# from the GitHub account that is active in `gh`. Run with --dry-run first and show the output to the user.
set -euo pipefail

UPSTREAM="DominikKriss/mixing-console-skills"
usage() {
  cat <<EOF
usage: contribute.sh --title "<PR title>" --body-file <file> [--branch <name>] [--email <commit email>] [--dry-run]
EOF
  exit 2
}

TITLE="" BODY="" BRANCH="" EMAIL="" DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --title) TITLE="$2"; shift 2 ;;
    --body-file) BODY="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    *) usage ;;
  esac
done
[ -n "$TITLE" ] && [ -n "$BODY" ] || usage
[ -f "$BODY" ] || { echo "body file not found: $BODY" >&2; exit 2; }
BODY="$(cd "$(dirname "$BODY")" && pwd -P)/$(basename "$BODY")"

command -v gh >/dev/null || { echo "gh (GitHub CLI) is not installed: https://cli.github.com" >&2; exit 3; }
LOGIN="$(gh api user -q .login 2>/dev/null)" || { echo "gh is not logged in: run 'gh auth login'" >&2; exit 3; }

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SKILL_NAME="$(basename "$SKILL_DIR")"

# An install that is a clone of the repo is used as is; a plain copy is diffed against a fresh clone.
REPO=""
if top="$(git -C "$SKILL_DIR" rev-parse --show-toplevel 2>/dev/null)" \
   && git -C "$top" remote get-url origin 2>/dev/null | grep -qi "$UPSTREAM"; then
  REPO="$top"
  REL="$(git -C "$SKILL_DIR" rev-parse --show-prefix)"
  REL="${REL%/}"
else
  TMP="$(mktemp -d)"
  KEEP_TMP=0
  trap 'if [ "$KEEP_TMP" = 1 ]; then echo "the commit is kept in $TMP/repo; retry with: bash $TMP/repo/$REL/scripts/contribute.sh --title ... --body-file ..." >&2; else rm -rf "$TMP"; fi' EXIT
  git clone -q "https://github.com/$UPSTREAM.git" "$TMP/repo"
  REPO="$TMP/repo"
  REL="$SKILL_NAME"
  [ -d "$REPO/$REL" ] || { echo "upstream has no folder $REL" >&2; exit 3; }
  rm -rf "${REPO:?}/$REL"
  cp -R "$SKILL_DIR" "$REPO/$REL"
  find "$REPO/$REL" \( -name __pycache__ -o -name .DS_Store \) -prune -exec rm -rf {} +
  echo "note: this install is not a git clone; changes are compared with upstream main, so anything upstream added since you copied the skill shows as removed."
fi

cd "$REPO"
git fetch -q origin refs/heads/main
UPSTREAM_MAIN="$(git rev-parse FETCH_HEAD)"
AHEAD="$(git rev-list "$UPSTREAM_MAIN..HEAD")"
CURRENT="$(git rev-parse --abbrev-ref HEAD)"
CHANGED="$(git status --porcelain -- "$REL")"
RESUME=0
if [ -z "$CHANGED" ]; then
  # A learn/ branch, or the branch named with --branch, with skill-only commits: an earlier run committed but didn't finish publishing.
  if { [ "${CURRENT#learn/}" != "$CURRENT" ] || [ "$CURRENT" = "$BRANCH" ]; } && [ -n "$AHEAD" ] \
     && [ -z "$(git diff --name-only "$UPSTREAM_MAIN" HEAD -- . ":(exclude)$REL")" ]; then
    RESUME=1
    BRANCH="$CURRENT"
  else
    echo "no changes in $REL"
    exit 1
  fi
fi
PENDING="$(git status --porcelain -z --untracked-files=all -- "$REL" | tr '\0' '\n')"
if grep -Eiq '\.(emo|scn|dat|snap|dmxf|dm7f|rpp|rpp-bak)$|__pycache__' <<<"$PENDING"; then
  echo "refusing: session / scene files are among the changes; keep them out of the skill folder" >&2
  exit 4
fi
HISTORY_HIT=0 HISTORY_OUTSIDE=0
for c in $(git rev-list "$UPSTREAM_MAIN..HEAD"); do
  NAMES="$(git diff-tree -r -m --root --no-commit-id --name-only -z "$c" | tr '\0' '\n')"
  if grep -Eiq '\.(emo|scn|dat|snap|dmxf|dm7f|rpp|rpp-bak)$' <<<"$NAMES"; then HISTORY_HIT=1; fi
  OUTSIDE_NAMES="$(grep -v -e '^$' -e "^$REL/" <<<"$NAMES" || true)"
  if [ -n "$OUTSIDE_NAMES" ]; then HISTORY_OUTSIDE=1; fi
done
if [ "$HISTORY_OUTSIDE" = 1 ]; then
  echo "refusing: an unpublished commit on this branch changes files outside $REL; they would be published with the history" >&2
  exit 4
fi
if [ "$HISTORY_HIT" = 1 ]; then
  echo "refusing: an unpublished commit on this branch holds a session / scene file; it would be published with the history" >&2
  exit 4
fi
OUTSIDE="$(git diff --cached --name-only -- . ":(exclude)$REL")"
if [ -n "$OUTSIDE" ]; then
  echo "refusing: files outside $REL are staged and would be committed too; unstage them first:" >&2
  echo "$OUTSIDE" >&2
  exit 4
fi
if [ "$RESUME" = 0 ] && [ -n "$AHEAD" ]; then
  echo "refusing: this branch has commits that aren't on upstream main; they would be published with the PR:" >&2
  git log --oneline "$UPSTREAM_MAIN..HEAD" >&2
  exit 4
fi

AUTHOR_EMAIL="${EMAIL:-${GIT_AUTHOR_EMAIL:-$(git config user.email || true)}}"
AUTHOR_NAME="${GIT_AUTHOR_NAME:-$(git config user.name || echo "$LOGIN")}"
[ -n "$BRANCH" ] || BRANCH="learn/$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//; s/-$//' | cut -c1-40)"

if [ "$LOGIN" = "${UPSTREAM%%/*}" ]; then PUSH_TO="origin (maintainer)"; HEAD="$BRANCH"
else PUSH_TO="fork $LOGIN/${UPSTREAM##*/}"; HEAD="$LOGIN:$BRANCH"; fi

echo "GitHub account : $LOGIN"
echo "commit author  : $AUTHOR_NAME <$AUTHOR_EMAIL>"
echo "branch         : $BRANCH -> $PUSH_TO"
echo "pull request   : $UPSTREAM  \"$TITLE\""
if [ "$RESUME" = 1 ]; then
  echo "resuming      : $BRANCH is already committed, publishing it"
  git --no-pager log --format='  %h %an <%ae> %s' "$UPSTREAM_MAIN..HEAD"
  git --no-pager diff --stat "$UPSTREAM_MAIN" HEAD -- "$REL"
else
  echo "files:"
  git status --porcelain --untracked-files=all -- "$REL" | sed 's/^/  /'
  git --no-pager diff --stat -- "$REL"
fi
if [ "$DRY" = 1 ]; then echo "dry run: nothing committed or pushed"; exit 0; fi

if [ "$RESUME" = 0 ]; then
  git checkout -q -b "$BRANCH"
  git add -- "$REL"
  GIT_AUTHOR_NAME="$AUTHOR_NAME" GIT_AUTHOR_EMAIL="$AUTHOR_EMAIL" \
    GIT_COMMITTER_NAME="$AUTHOR_NAME" GIT_COMMITTER_EMAIL="$AUTHOR_EMAIL" git commit -q -m "$TITLE"
fi
KEEP_TMP=1

if [ "$LOGIN" = "${UPSTREAM%%/*}" ]; then
  git push -q -u origin "$BRANCH"
else
  gh repo fork "$UPSTREAM" --clone=false >/dev/null 2>&1 || true
  FORK_NAME="$(gh api "repos/$UPSTREAM/forks" --paginate --jq ".[] | select(.owner.login == \"$LOGIN\") | .name" 2>/dev/null | head -n1 || true)"
  FORK_URL="https://github.com/$LOGIN/${FORK_NAME:-${UPSTREAM##*/}}.git"
  pushed=0
  for _ in 1 2 3 4 5; do
    if git push -q "$FORK_URL" "$BRANCH"; then pushed=1; break; fi
    sleep 3
  done
  [ "$pushed" = 1 ] || { echo "push to $FORK_URL failed; the commit is on local branch $BRANCH" >&2; exit 5; }
fi

EXISTING="$(gh pr list --repo "$UPSTREAM" --head "$BRANCH" --json url,headRepositoryOwner \
  -q ".[] | select(.headRepositoryOwner.login == \"$LOGIN\") | .url" 2>/dev/null || true)"
if [ -n "$EXISTING" ]; then
  echo "pull request already open: $EXISTING"
  KEEP_TMP=0
  exit 0
fi
PR_URL="$(gh pr create --repo "$UPSTREAM" --base main --head "$HEAD" --title "$TITLE" --body-file "$BODY")" \
  || { echo "opening the PR failed; run this script again on branch $BRANCH to retry" >&2; exit 5; }
echo "$PR_URL"
KEEP_TMP=0
# CodeRabbit reviews repos under 10 stars only on request.
gh pr comment "$PR_URL" --body "@coderabbitai review" >/dev/null || echo "note: couldn't request the CodeRabbit review; comment '@coderabbitai review' on the PR"
