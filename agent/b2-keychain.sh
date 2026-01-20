#!/bin/bash
#
# B2 Keychain Helper
#
# Store and retrieve Backblaze B2 credentials from macOS Keychain
#
# Usage:
#   ./b2-keychain.sh store        # Store credentials in keychain (interactive)
#   ./b2-keychain.sh get          # Print export commands for credentials
#   eval $(./b2-keychain.sh get)  # Set credentials as env vars
#   ./b2-keychain.sh run <cmd>    # Run b2 command with keychain credentials
#

SERVICE_NAME="rmirror-b2"
KEY_ID_ACCOUNT="b2-key-id"
KEY_SECRET_ACCOUNT="b2-key-secret"

store_credentials() {
    echo "Storing B2 credentials in macOS Keychain..."
    echo ""

    read -p "B2 Application Key ID: " KEY_ID
    read -sp "B2 Application Key: " KEY_SECRET
    echo ""

    # Store in keychain
    security add-generic-password -U -s "$SERVICE_NAME" -a "$KEY_ID_ACCOUNT" -w "$KEY_ID" 2>/dev/null || \
    security add-generic-password -s "$SERVICE_NAME" -a "$KEY_ID_ACCOUNT" -w "$KEY_ID"

    security add-generic-password -U -s "$SERVICE_NAME" -a "$KEY_SECRET_ACCOUNT" -w "$KEY_SECRET" 2>/dev/null || \
    security add-generic-password -s "$SERVICE_NAME" -a "$KEY_SECRET_ACCOUNT" -w "$KEY_SECRET"

    echo ""
    echo "✓ Credentials stored in Keychain under service '$SERVICE_NAME'"
    echo ""
    echo "To use with b2 CLI:"
    echo "  eval \$(./b2-keychain.sh get)"
    echo "  b2 account authorize"
    echo ""
    echo "Or use the release script which handles this automatically."
}

get_credentials() {
    KEY_ID=$(security find-generic-password -s "$SERVICE_NAME" -a "$KEY_ID_ACCOUNT" -w 2>/dev/null)
    KEY_SECRET=$(security find-generic-password -s "$SERVICE_NAME" -a "$KEY_SECRET_ACCOUNT" -w 2>/dev/null)

    if [ -z "$KEY_ID" ] || [ -z "$KEY_SECRET" ]; then
        echo "# ERROR: B2 credentials not found in Keychain" >&2
        echo "# Run: ./b2-keychain.sh store" >&2
        exit 1
    fi

    echo "export B2_APPLICATION_KEY_ID='$KEY_ID'"
    echo "export B2_APPLICATION_KEY='$KEY_SECRET'"
}

run_command() {
    eval $(get_credentials)
    b2 "$@"
}

case "${1:-}" in
    store)
        store_credentials
        ;;
    get)
        get_credentials
        ;;
    run)
        shift
        run_command "$@"
        ;;
    *)
        echo "B2 Keychain Helper"
        echo ""
        echo "Usage:"
        echo "  $0 store         Store B2 credentials in Keychain"
        echo "  $0 get           Print export commands for credentials"
        echo "  $0 run <cmd>     Run b2 command with Keychain credentials"
        echo ""
        echo "Examples:"
        echo "  $0 store"
        echo "  eval \$($0 get)"
        echo "  $0 run file upload bucket file.txt remote.txt"
        ;;
esac
