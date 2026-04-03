# Git & GitHub Privacy Scrubbing Guide

Template for scrubbing personal emails, API keys, and sensitive files from any public repo.

---

## 1. Prerequisites

```bash
brew install git-filter-repo
```

## 2. Set GitHub email privacy (one-time)

Go to **GitHub.com → Settings → Emails** and enable:
- "Keep my email addresses private"
- "Block command line pushes that expose my email"

Then set your global git config to use the noreply address:

```bash
git config --global user.email "<GITHUB_USER_ID>+<GITHUB_USERNAME>@users.noreply.github.com"
git config --global user.name "<GITHUB_USERNAME>"
```

> Find your exact noreply address at the bottom of GitHub → Settings → Emails.

## 3. Audit the repo

### 3a. Find emails in commit history

```bash
git log --all --format='%ae' | sort -u
```

### 3b. Find hardcoded secrets

```bash
# Search for API keys, tokens, passwords in tracked files
grep -rn 'api_key\|API_KEY\|secret\|password\|token' --include='*.py' --include='*.js' --include='*.toml' --include='*.yml'

# Check for .env files that shouldn't be tracked
git ls-files | grep -iE '\.env$|credentials|\.plist|\.venv|node_modules'
```

### 3c. Check for sensitive files in git history (even if deleted)

```bash
git log --all --diff-filter=A --name-only --format='' | grep -iE '\.env$|\.pem|\.key|credentials' | sort -u
```

## 4. Fix .gitignore before rewriting

Add entries for anything that shouldn't be tracked:

```gitignore
# Environment variables
.env
.env.local
.env.production

# Credentials / keys
*.pem
*.key
credentials.*

# Virtual environments
.venv/
venv/
node_modules/

# macOS launchd plists (contain local paths/username)
*.plist

# OS files
.DS_Store

# IDE
.vscode/
.idea/
```

Remove already-tracked sensitive files (keeps them locally):

```bash
git rm --cached -r .venv/ node_modules/ 2>/dev/null
git rm --cached .env *.plist 2>/dev/null
git add .gitignore
git commit -m "Update .gitignore and untrack sensitive files"
```

## 5. Rewrite history

### 5a. Create a mailmap file

Map old emails to the GitHub noreply address. One line per email to scrub:

```bash
cat > /tmp/mailmap <<'EOF'
NewName <new@email> <old1@email>
NewName <new@email> <old2@email>
EOF
```

Example:

```bash
cat > /tmp/mailmap <<'EOF'
myuser <12345678+myuser@users.noreply.github.com> <personal@gmail.com>
myuser <12345678+myuser@users.noreply.github.com> <work@company.com>
EOF
```

### 5b. Clone bare and rewrite

```bash
# Fresh bare clone (git-filter-repo requires this)
git clone --bare /path/to/local/repo /tmp/repo_rewrite
cd /tmp/repo_rewrite

# Rewrite emails only
git filter-repo --mailmap /tmp/mailmap --force

# Rewrite emails AND scrub a secret from file contents
git filter-repo --mailmap /tmp/mailmap \
  --replace-text <(echo 'YOUR_SECRET_VALUE==>REDACTED') \
  --force
```

> You can add multiple `--replace-text` entries or put them all in a file (one per line).

### 5c. Verify before pushing

```bash
# Check emails are clean
git log --all --format='%ae' | sort -u

# Check secrets are gone
git log --all -p | grep -c 'YOUR_SECRET_VALUE'
# Should output: 0
```

## 6. Force push to GitHub

```bash
cd /tmp/repo_rewrite
git remote add origin https://github.com/<USER>/<REPO>.git
git push --mirror --force origin
```

## 7. Sync your local repo

```bash
cd /path/to/local/repo
git fetch origin
git reset --hard origin/main

# Purge old reflog so old commits aren't recoverable locally
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

## 8. Clean up

```bash
rm -rf /tmp/repo_rewrite /tmp/mailmap
```

## 9. Post-rewrite checklist

- [ ] Rotate any API keys/secrets that were in git history — they're compromised even after scrubbing
- [ ] Check GitHub cached commits: visit `https://github.com/<USER>/<REPO>/commit/<OLD_SHA>` — if still accessible, contact [GitHub Support](https://support.github.com/request) to purge cached refs
- [ ] Check if anyone forked the repo before the rewrite — their fork still has the old history
- [ ] Repeat for other repos that have the same email exposure

## Quick reference: privacy options compared

| Action | Public can see commits? | Emails scrubbed? |
|--------|------------------------|------------------|
| **Archive repo** | Yes | No |
| **Make private** | No (hidden, not scrubbed) | No |
| **filter-repo + force push** | Yes, but emails replaced | Yes |
| **Delete + recreate** | Old history gone | Yes |

## Notes

- `git filter-repo` rewrites every commit SHA — forks and open PRs referencing old SHAs will break
- GitHub noreply emails are tied to your account, not guessable without your user ID
- The `--mirror` push updates all branches and tags, not just `main`
- If the repo has collaborators, they need to `git fetch && git reset --hard origin/main` after the rewrite
