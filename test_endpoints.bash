#!/bin/bash
set -euo pipefail

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
RESET="\033[0m"

# Config
BASE_URL="http://localhost:8000/v1/auth"
TEST_EMAIL="test@example.com"
TEST_PASS="TestPassword123"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

DEBUG=false
AUTO_CONFIRM=false

# Parse flags
for arg in "$@"; do
    case "$arg" in
        --debug) DEBUG=true ;;
        --confirm) AUTO_CONFIRM=true ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# Logging
log() {
    local level="$1"; shift
    local color
    case "$level" in
        INFO) color="$CYAN" ;;
        WARN) color="$YELLOW" ;;
        OK) color="$GREEN" ;;
        ERR) color="$RED" ;;
        *) color="$RESET" ;;
    esac
    local ts
    ts=$(date +"%H:%M:%S")
    echo -e "${color}[$ts][$level] $*${RESET}"
}

# Confirmation
confirm() {
    if [ "$AUTO_CONFIRM" = true ]; then
        log INFO "Confirmation skipped (--confirm)."
        return
    fi
    read -p "$(echo -e "${YELLOW}Proceed with tests? (Y/n): ${RESET}")" choice
    case "$choice" in
        y|Y|"" ) ;;
        n|N ) log WARN "Test execution cancelled."; exit 0 ;;
        * ) log ERR "Invalid choice. Use Y or n."; confirm ;;
    esac
}

# HTTP wrapper
curl_json() {
    curl -s -X "$1" "$BASE_URL/$2" \
         -H "Authorization: Bearer ${3:-}" \
         -H "Content-Type: application/json" \
         -d "${4:-}"
}

# Token check
check_token() { jq -e '.access_token' <<< "$1" >/dev/null; }

# Start
confirm
log INFO "Testing authentication endpoints on $BASE_URL"

# Register
log INFO "Registering test user..."
register_payload=$(jq -n --arg e "$TEST_EMAIL" --arg p "$TEST_PASS" \
  '{email_address:$e,password:$p,first_name:"Test",last_name:"User"}')
register_response=$(curl_json POST "register" "" "$register_payload")
echo "$register_response" > "$LOG_DIR/register.json"
$DEBUG && log WARN "Register Response: $register_response"

if check_token "$register_response"; then
    access_token=$(jq -r '.access_token' <<< "$register_response")
    log OK "Registration successful."
else
    log ERR "Registration failed."; exit 1
fi

# Duplicate register
log INFO "Testing duplicate registration..."
dup_response=$(curl_json POST "register" "" "$register_payload")
echo "$dup_response" > "$LOG_DIR/duplicate_register.json"
$DEBUG && log WARN "Duplicate Register Response: $dup_response"

if jq -e '.detail' <<< "$dup_response" >/dev/null; then
    log OK "Duplicate registration correctly failed."
else
    log ERR "Duplicate registration test failed."; exit 1
fi

# Login
log INFO "Testing login..."
login_payload=$(jq -n --arg e "$TEST_EMAIL" --arg p "$TEST_PASS" \
  '{email_address:$e,password:$p}')
login_response=$(curl_json POST "login" "" "$login_payload")
echo "$login_response" > "$LOG_DIR/login.json"
$DEBUG && log WARN "Login Response: $login_response"

if check_token "$login_response"; then
    access_token=$(jq -r '.access_token' <<< "$login_response")
    log OK "Login successful."
else
    log ERR "Login failed."; exit 1
fi

# Refresh
log INFO "Testing token refresh..."
refresh_response=$(curl_json POST "refresh" "$access_token")
echo "$refresh_response" > "$LOG_DIR/refresh.json"
$DEBUG && log WARN "Refresh Response: $refresh_response"

if check_token "$refresh_response"; then
    access_token=$(jq -r '.access_token' <<< "$refresh_response")
    log OK "Token refresh successful."
else
    log ERR "Token refresh failed."; exit 1
fi

# Fetch user info
log INFO "Fetching user info..."
user_info_response=$(curl_json GET "fetch" "$access_token")
echo "$user_info_response" > "$LOG_DIR/user_info.json"
$DEBUG && log WARN "User Info Response: $user_info_response"

if jq -e '.email_address' <<< "$user_info_response" >/dev/null; then
    log OK "User info fetched successfully."
else
    log ERR "User info fetch failed."; exit 1
fi

# Delete user
log INFO "Deleting test user..."
delete_response=$(curl_json DELETE "delete" "$access_token")
echo "$delete_response" > "$LOG_DIR/delete.json"
$DEBUG && log WARN "Delete Response: $delete_response"

log OK "Test sequence complete."
