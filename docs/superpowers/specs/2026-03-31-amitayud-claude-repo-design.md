# amitayud-claude Repository Design

**Date:** 2026-03-31
**Status:** Approved
**Author:** amitayu with Claude Code

## Overview

Create a private GitHub repository `netSkope/amitayud-claude` to track user-authored Claude Code configuration files from `~/.claude/`. This repository serves as version-controlled backup and documentation of personal Claude Code setup, following the proven pattern established by `netSkope/stevemns-claude`.

## Goals

1. **Track user-authored configuration**: Version control all files that define how Claude Code behaves (CLAUDE.md, settings.json, skills, scripts)
2. **Exclude runtime artifacts**: Never commit ephemeral data (history, sessions, cache, etc.)
3. **Preserve existing setup**: Keep working AWS/Bedrock configuration and custom scripts intact
4. **Enable portability**: Allow configuration to be cloned and replicated on other machines
5. **Provide organization**: Create clear structure for skills, scripts, commands, and documentation

## Non-Goals

- C++-specific configuration (will be in separate `amitayud-claude-world` repository)
- Tracking individual project work or code
- Replacing `~/gitcode/` repositories for official deliverables
- Modifying Claude Code's runtime behavior

## Architecture

### Repository Structure

Initialize git repository directly in `~/.claude/` directory with the following tracked structure:

```
~/.claude/
├── .git/                    # Git metadata
├── .gitignore              # Deny-by-default pattern
├── README.md               # Repository documentation
├── CLAUDE.md               # Global instructions for all sessions
├── settings.json           # App settings (AWS, plugins, hooks)
├── status-line.sh          # Custom status line script
├── skills/                 # Custom skill definitions
│   └── commit/
│       └── SKILL.md        # Existing commit skill
├── commands/               # Custom slash commands (initially empty)
├── scripts/                # Helper scripts (initially empty)
├── docs/                   # Reference documentation (initially empty)
└── plans/                  # Ad hoc work tracking
    └── whimsical-swinging-crescent.md

# Explicitly ignored (runtime artifacts):
├── history.jsonl           # Conversation history
├── sessions/               # Session state
├── cache/                  # Plugin/download cache
├── backups/                # Automatic backups
├── debug/                  # Debug logs
├── downloads/              # Downloaded files
├── file-history/           # File edit history
├── ide/                    # IDE integration state
├── paste-cache/            # Paste cache
├── plugins/                # Plugin cache (source-controlled separately)
├── projects/               # Per-project data (memory, todos)
├── session-env/            # Session environment
├── shell-snapshots/        # Shell snapshots
└── tasks/                  # Task runtime data
```

### Key Design Decisions

**1. Initialize in ~/.claude/ (not separate directory)**

**Rationale:** Claude Code expects configuration at `~/.claude/`. Initializing git directly in this directory:
- Requires no symlinks or directory moves
- Works seamlessly with Claude Code's file access patterns
- Matches stevemns-claude's proven approach
- Allows editing files in place and committing naturally

**2. Deny-by-default .gitignore pattern**

**Rationale:** Runtime artifacts outnumber user-authored files. Pattern:
```gitignore
# Ignore everything
*

# Allowlist user-authored files
!.gitignore
!README.md
!CLAUDE.md
!settings.json
!status-line.sh

# Allowlist directories
!skills/
!skills/**
!commands/
!commands/**
!scripts/
!scripts/**
!docs/
!docs/**
!plans/
!plans/**
```

This approach:
- Prevents accidental tracking of sensitive data (history.jsonl contains full conversations)
- Scales naturally (new runtime directories are automatically ignored)
- Makes intent explicit (only files we explicitly allow are tracked)
- Protects against large file commits (session data can exceed 100MB)

**3. Full directory structure from day one**

**Rationale:** Create `commands/`, `scripts/`, `docs/`, `plans/` upfront even if initially empty:
- Provides clear organizational homes for future additions
- Matches established stevemns-claude pattern
- Eliminates "where should this go?" decisions later
- Uses .gitkeep files to track empty directories in git

**4. Private GitHub repository in netSkope org**

**Rationale:** Configuration contains:
- AWS account references (NSBedrockViewer-242201274356)
- Netskope-specific plugin configurations
- Internal marketplace references (netSkope/claude-skills)
- Work patterns and preferences

While not containing credentials directly, this context is internal to Netskope.

## Component Details

### Core Configuration Files

**README.md**
- Documents repository purpose
- Explains tracked vs. ignored files
- Provides structure table mapping paths to purposes
- Notes .gitignore strategy
- Links to Claude Code documentation

**CLAUDE.md**
- Global instructions loaded into every Claude Code session
- Generic preferences (not language-specific)
- Covers:
  - Communication style preferences
  - Commit conventions
  - General coding standards
  - Testing philosophy
  - Workflow preferences (plans, parallel agents, git usage)
  - Configuration file references
- Will be populated with comprehensive best practices initially
- User can customize over time

**settings.json** (existing, preserve as-is)
- AWS authentication: `awsAuthRefresh` command
- Environment variables: AWS_PROFILE, CLAUDE_CODE_USE_BEDROCK, AWS_REGION
- Enabled plugins: eng-skills@netskope, superpowers@claude-plugins-official
- Custom marketplace: netSkope/claude-skills
- Status line configuration

**status-line.sh** (existing, preserve as-is)
- Bash script that processes JSON input
- Displays context window usage percentage
- Displays session cost in USD
- Output format: `ctx: {pct}% | ${cost}`

### Directory Purposes

**skills/**
- User-created skill definitions (SKILL.md files)
- Each skill is a subdirectory with SKILL.md
- Currently contains: `commit/SKILL.md`
- Future additions: any custom workflow automations

**commands/**
- Custom slash command definitions
- Initially empty, ready for use
- Would contain command definitions that extend Claude Code CLI

**scripts/**
- Helper shell scripts invoked by hooks or skills
- Initially empty, ready for use
- Examples: notification scripts, validation helpers, session tracking

**docs/**
- Reference documentation loaded on demand
- Initially empty, ready for use
- Examples: internal APIs, debugging guides, tool documentation

**plans/**
- Ad hoc work tracking and planning documents
- Currently contains: `whimsical-swinging-crescent.md`
- Generated by Claude Code's plan mode
- Useful for historical reference of approaches taken

## Git Workflow

### Initial Setup

1. `cd ~/.claude/`
2. `git init -b main`
3. Create .gitignore with deny-by-default pattern
4. Create README.md and CLAUDE.md
5. Create empty directories: commands/, scripts/, docs/
6. Add .gitkeep files to empty directories
7. Stage all allowlisted files
8. Commit: "Initial configuration for amitayud-claude"
9. Create GitHub repo: `gh repo create netSkope/amitayud-claude --private --description "Claude Code configuration for amitayu"`
10. Push to remote: `git push -u origin main`

### Ongoing Usage

**Normal workflow:**
- Edit configuration files in `~/.claude/` as needed
- Claude Code operates normally (no interruption)
- When changes are significant (new skill, updated CLAUDE.md), commit them
- Push to GitHub periodically to backup configuration

**Adding new skills:**
```bash
# Create skill directory and SKILL.md
mkdir -p ~/.claude/skills/my-skill
vim ~/.claude/skills/my-skill/SKILL.md

# Git automatically tracks (allowlisted by skills/**)
git add skills/my-skill/
git commit -m "Add my-skill for X workflow"
git push
```

**Adding helper scripts:**
```bash
# Create script
vim ~/.claude/scripts/my-helper.sh

# Git automatically tracks (allowlisted by scripts/**)
git add scripts/my-helper.sh
git commit -m "Add helper script for Y"
git push
```

### Safety Guarantees

The .gitignore pattern ensures:
- `git status` never shows runtime artifacts
- `git add .` is safe (only allowlisted files can be staged)
- `git add -A` is safe
- Sensitive data in history.jsonl, sessions/, projects/ cannot be committed
- Large runtime files cannot bloat repository

## Verification & Testing

### Post-Setup Verification

After initial setup, verify:

1. **Git status is clean:**
   ```bash
   cd ~/.claude/
   git status
   # Should show: "nothing to commit, working tree clean"
   ```

2. **All user-authored files tracked:**
   ```bash
   git ls-files
   # Should list: .gitignore, README.md, CLAUDE.md, settings.json,
   # status-line.sh, skills/commit/SKILL.md, plans/*.md, .gitkeep files
   ```

3. **Runtime artifacts ignored:**
   ```bash
   git status --ignored
   # Should show: history.jsonl, sessions/, cache/, etc. as ignored
   ```

4. **GitHub repository accessible:**
   ```bash
   gh repo view netSkope/amitayud-claude
   # Should show: private repository, correct description
   ```

5. **Claude Code still works:**
   - Start new Claude Code session
   - Check status line displays correctly
   - Verify plugins loaded (eng-skills, superpowers)
   - Verify AWS/Bedrock authentication works

### Ongoing Health Checks

Periodically verify:
- No large files accidentally committed: `git ls-files | xargs ls -lh | sort -k5 -h`
- Remote backup current: `git status` shows no unpushed commits
- .gitignore still effective: `git status` shows no untracked runtime files

## Migration from Current State

**Current state analysis:**
- `~/.claude/` already exists with working configuration
- AWS/Bedrock setup functional
- Plugins enabled and working
- Custom status line operational
- One custom skill exists (commit)
- One plan file exists

**Migration approach:**
- No data migration needed (initialize git in place)
- No file moves needed
- No configuration changes needed
- Zero disruption to Claude Code operation
- Simply add git tracking to existing directory

**Rollback plan:**
If issues arise:
```bash
cd ~/.claude/
rm -rf .git .gitignore
# Configuration files remain untouched, Claude Code continues working
```

## Future Enhancements

**Potential additions (out of scope for initial setup):**

1. **LEARNINGS.md**: Trial-and-error knowledge base (like stevemns-claude)
2. **Git hooks**: Pre-commit validation, notification scripts
3. **Additional skills**: C++ debugging workflows, code review automation
4. **Documentation**: Best practices, troubleshooting guides
5. **Backup automation**: Scheduled commits via cron or systemd timer
6. **Multi-machine sync**: Instructions for cloning configuration to other machines

## Relationship to amitayud-claude-world

**amitayud-claude** (this repo):
- Global Claude Code configuration
- Applies to ALL Claude Code sessions
- Generic preferences and workflows
- Lives at `~/.claude/`

**amitayud-claude-world** (future repo):
- Workspace organization for different contexts
- C++-specific configurations and instructions
- Per-project CLAUDE.md files
- Lives at separate directory (TBD), referenced via projects

Both repositories serve distinct purposes and do not conflict.

## Success Criteria

The implementation is successful when:

1. ✅ Git repository initialized in `~/.claude/` with main branch
2. ✅ All user-authored files tracked (settings.json, status-line.sh, skills, etc.)
3. ✅ All runtime artifacts ignored (history, sessions, cache, etc.)
4. ✅ Private GitHub repository created at `netSkope/amitayud-claude`
5. ✅ Initial commit pushed to remote
6. ✅ Claude Code operates without interruption
7. ✅ `git status` is clean (no untracked/unstaged user files)
8. ✅ README.md and CLAUDE.md provide clear documentation
9. ✅ Directory structure ready for future additions
10. ✅ No sensitive data committed to repository

## Implementation Plan Next Steps

After this design is approved:
1. Invoke `superpowers:writing-plans` skill to create detailed implementation plan
2. Execute plan to set up repository
3. Verify all success criteria met
4. Document any learnings or deviations

## References

- Inspiration: https://github.com/netSkope/stevemns-claude
- Claude Code documentation: https://docs.anthropic.com/en/docs/claude-code
- Git deny-by-default pattern: https://git-scm.com/docs/gitignore
