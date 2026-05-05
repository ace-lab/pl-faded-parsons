function git-sync-tracked-from-branch --description 'Restore tracked files from another branch into the current working tree'
    if test (count $argv) -lt 1
        echo "Usage: git-sync-tracked-from-branch <source-branch>" >&2
        return 1
    end

    set -l source_branch $argv[1]

    if not git rev-parse --verify "$source_branch" >/dev/null 2>&1
        echo "Unknown branch or revision: $source_branch" >&2
        return 1
    end

    set -l repo_root (git rev-parse --show-toplevel 2>/dev/null)
    or return 1

    cd "$repo_root"

    # Fish keeps path elements intact here, so tracked files with spaces still work.
    set -l tracked_files (git ls-files -z | string split0)
    set -l source_files (git ls-tree -r -z --name-only "$source_branch" | string split0)

    set -l restored 0
    for file in $tracked_files
        if contains -- "$file" $source_files
            git restore --source="$source_branch" --worktree -- "$file"
            or return 1
            set restored (math $restored + 1)
        end
    end

    if test $restored -eq 0
        echo "No tracked files from the current branch were found on $source_branch." >&2
        return 1
    end
end
