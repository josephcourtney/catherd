if set -q KITTY_WINDOW_ID; and set -q ATUIN_SESSION
    mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}/catherd"
    echo "$ATUIN_SESSION $KITTY_WINDOW_ID" > "${XDG_CACHE_HOME:-$HOME/.cache}/catherd/atuin_kitty_${KITTY_WINDOW_ID}"
end
