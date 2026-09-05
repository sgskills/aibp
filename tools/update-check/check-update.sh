#!/bin/sh
# Generated copies are managed by tools/sync-update-check.ps1.
# POSIX sh + curl + system utilities. Remote content is never executed.
LC_ALL=C
export LC_ALL
umask 077
now_arg= cache_root= response_file= test_url=
while [ "$#" -gt 0 ]; do
    [ "$#" -ge 2 ] || exit 0
    case "$1" in
        --now-seconds) now_arg=$2 ;;
        --cache-root) cache_root=$2 ;;
        --response-file) response_file=$2 ;;
        --test-url) test_url=$2 ;;
        *) exit 0 ;;
    esac
    shift 2
done

valid_seconds() {
    case "$1" in ''|*[!0-9]*|0[0-9]*) return 1 ;; esac
    [ "${#1}" -le 12 ]
}

valid_version() {
    printf '%s\n' "$1" | awk -F. 'NF != 3 {exit 1} {for(i=1;i<=3;i++) if ($i !~ /^(0|[1-9][0-9]*)$/ || length($i)>10 || $i+0>2147483647) exit 1}'
}

read_version() {
    [ -f "$1" ] || return 1
    version_size=$(wc -c < "$1") || return 1
    [ "$version_size" -le 64 ] || return 1
    # Check raw length before shell substitution can erase newlines or NUL.
    # BINMODE is honored by MSYS awk; on Unix it is an ordinary unused variable.
    version_value=$(awk -v size="$version_size" 'BEGIN {BINMODE=3} NR>1 {bad=1} NR==1 {s=$0; if(sub(/\r$/, "",s)){if(size!=length(s)+2)bad=1} else if(size!=length(s) && size!=length(s)+1)bad=1; if(s !~ /^[0-9.]+$/)bad=1} END {if(bad || NR!=1)exit 1; printf "%s",s}' "$1") || return 1
    valid_version "$version_value" || return 1
    printf '%s' "$version_value"
}

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd -P) || exit 0
local_version=$(read_version "$script_dir/update-version.txt" 2>/dev/null) || exit 0
if [ -n "$now_arg" ]; then now=$now_arg; else now=$(date +%s) || exit 0; fi
valid_seconds "$now" || exit 0
url=https://raw.githubusercontent.com/sgskills/aibp/main/VERSION
if [ -n "$test_url" ]; then
    printf '%s\n' "$test_url" | awk 'NR>1 {bad=1} /^http:\/\/127\.0\.0\.1:[1-9][0-9]*\/[^[:space:]#]*$/ {split($0,a,":"); split(a[3],p,"/"); if(length(p[1])<=5 && p[1]+0<=65535) ok=1} END {exit (bad || !ok)}' || exit 0
    url=$test_url
fi
if [ -z "$cache_root" ]; then
    case "$(uname -s)" in
        Darwin) [ -n "${HOME:-}" ] || exit 0; cache_root=$HOME/Library/Caches/SGSkills/aibp ;;
        *) if [ -n "${XDG_CACHE_HOME:-}" ]; then cache_root=$XDG_CACHE_HOME/sgskills/aibp
           else [ -n "${HOME:-}" ] || exit 0; cache_root=$HOME/.cache/sgskills/aibp; fi ;;
    esac
fi
case "$cache_root" in /*) ;; *) exit 0 ;; esac
cache=$cache_root/$local_version
mkdir -p -- "$cache" 2>/dev/null || exit 0
lock=$cache/attempt.lock
owned_lock= temp_file= response_temp=
cleanup() {
    [ -z "$temp_file" ] || rm -f -- "$temp_file" 2>/dev/null
    [ -z "$response_temp" ] || rm -f -- "$response_temp" 2>/dev/null
    if [ "$owned_lock" = yes ]; then
        if [ "$(cat "$lock/owner" 2>/dev/null)" = "$owner" ]; then
            rm -f -- "$lock/owner" 2>/dev/null
            rmdir -- "$lock" 2>/dev/null
        fi
    fi
    return 0
}
trap cleanup EXIT
trap 'exit 0' HUP INT TERM
real_now=$(date +%s) || exit 0
owner="$$ $real_now"
if ! mkdir -- "$lock" 2>/dev/null; then
    # Both the primary lock and the empty reclamation guard have a 30s lease.
    # Read mtimes before mkdir changes their parent's modification time.
    lock_time=$(stat -c %Y "$lock" 2>/dev/null) || lock_time=$(stat -f %m "$lock" 2>/dev/null)
    recovery_time=$(stat -c %Y "$lock/recovery" 2>/dev/null) || recovery_time=$(stat -f %m "$lock/recovery" 2>/dev/null)
    if valid_seconds "$recovery_time" && [ "$real_now" -ge "$recovery_time" ] && [ "$((real_now - recovery_time))" -ge 30 ]; then
        rmdir -- "$lock/recovery" 2>/dev/null
    fi
    # The empty guard serializes stale-lock reclamation. Re-read owner under it.
    if mkdir -- "$lock/recovery" 2>/dev/null; then
        lease=$(cat "$lock/owner" 2>/dev/null)
        lease_time=${lease#* }
        if ! valid_seconds "$lease_time"; then
            lease_time=$lock_time
        fi
        if valid_seconds "$lease_time" && [ "$real_now" -ge "$lease_time" ] && [ "$((real_now - lease_time))" -ge 30 ]; then
            stale=$cache/stale-lock-$$-$real_now
            if mv -- "$lock" "$stale" 2>/dev/null; then
                rm -f -- "$stale/owner" 2>/dev/null
                rmdir -- "$stale/recovery" "$stale" 2>/dev/null
            fi
        else
            rmdir -- "$lock/recovery" 2>/dev/null
        fi
    fi
    mkdir -- "$lock" 2>/dev/null || exit 0
fi
printf '%s' "$owner" > "$lock/owner" 2>/dev/null || { rmdir -- "$lock" 2>/dev/null; exit 0; }
owned_lock=yes
attempt=$cache/last-attempt.txt
repair=no
if [ -f "$attempt" ]; then
    size=$(wc -c < "$attempt" 2>/dev/null) || exit 0
    previous=
    if [ "$size" -le 12 ]; then
        previous=$(awk 'BEGIN {BINMODE=3} NR>1 {bad=1} NR==1 {s=$0} END {if(!bad && NR==1 && s ~ /^(0|[1-9][0-9]*)$/)printf "%s",s}' "$attempt" 2>/dev/null)
    fi
    [ "$size" -eq "${#previous}" ] || previous=
    if ! valid_seconds "$previous"; then repair=yes
    elif [ "$previous" -gt "$now" ]; then repair=yes
    elif [ "$((now - previous))" -lt 2592000 ]; then exit 0
    fi
elif [ -e "$attempt" ]; then exit 0
fi
temp_file=$(mktemp "$cache/attempt-XXXXXXXX" 2>/dev/null) || exit 0
printf '%s' "$now" > "$temp_file" 2>/dev/null || exit 0
[ "$(cat "$lock/owner" 2>/dev/null)" = "$owner" ] || exit 0
mv -f -- "$temp_file" "$attempt" 2>/dev/null || exit 0
temp_file=
cleanup
owned_lock=
[ "$repair" = no ] || exit 0
if [ -n "$response_file" ]; then remote_version=$(read_version "$response_file" 2>/dev/null) || exit 0
else
    command -v curl >/dev/null 2>&1 || exit 0
    response_temp=$(mktemp "$cache/response-XXXXXXXX" 2>/dev/null) || exit 0
    # curl's total deadline covers connect, headers and body; redirects and proxy use are disabled.
    status=$(curl --disable --silent --fail --noproxy '*' --connect-timeout 5 --max-time 5 --max-filesize 64 --proto '=http,https' --user-agent 'AIBP-update-check/1' --write-out '%{http_code}' --output "$response_temp" "$url" 2>/dev/null) || exit 0
    [ "$status" = 200 ] || exit 0
    remote_version=$(read_version "$response_temp" 2>/dev/null) || exit 0
fi
if awk -v local="$local_version" -v remote="$remote_version" 'BEGIN {split(local,a,"."); split(remote,b,"."); for(i=1;i<=3;i++){if(b[i]+0>a[i]+0)exit 0; if(b[i]+0<a[i]+0)exit 1} exit 1}'; then
    printf 'AIBP 源码有新版本 v%s（当前 v%s）：https://github.com/sgskills/aibp\n' "$remote_version" "$local_version"
fi
exit 0
