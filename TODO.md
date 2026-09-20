# Immediate work

- Run `just check` on the current tree. It now runs real bash/zsh/fish/csh snippet validation through the standalone `test-shell-integration` gate before pytest.
- Fix any remaining gate failures before treating the current 1.0.0 tree as release-rehearsed.
- Before tagging and publishing, ensure the tag points at the exact tree that passed the final release rehearsal.
