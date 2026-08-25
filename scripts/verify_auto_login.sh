#!/bin/bash
# verify_auto_login.sh — Check if auto-login is configured
# LaunchAgents only run when a user is logged in.
# If the Mac Mini reboots without auto-login, nothing runs.

echo "=== Auto-Login Check ==="
echo ""

# Check if auto-login is set
AUTOLOGIN_USER=$(sudo defaults read /Library/Preferences/com.apple.loginwindow autoLoginUser 2>/dev/null || echo "NOT SET")

if [ "$AUTOLOGIN_USER" == "NOT SET" ]; then
    echo "⚠️  AUTO-LOGIN IS NOT CONFIGURED"
    echo ""
    echo "  LaunchAgents require a logged-in user session."
    echo "  If the Mac Mini reboots, trading will NOT start until you log in."
    echo ""
    echo "  To enable auto-login:"
    echo "    System Settings → Users & Groups → Login Options → Automatic Login → clawbot"
    echo ""
    echo "  Or via command line (requires admin):"
    echo "    sudo defaults write /Library/Preferences/com.apple.loginwindow autoLoginUser clawbot"
    echo ""
    exit 1
else
    echo "✓ Auto-login configured for user: $AUTOLOGIN_USER"
    echo "  LaunchAgents will start automatically after reboot."
fi

echo ""

# Check if Energy Saver prevents sleep
SLEEP_DISABLED=$(pmset -g | grep -c "sleep.*0" || echo "0")
if [ "$SLEEP_DISABLED" == "0" ]; then
    echo "⚠️  Mac may go to sleep (which pauses launchd timers)"
    echo "  To prevent sleep: sudo pmset -a disablesleep 1"
    echo "  Or: System Settings → Energy Saver → Prevent automatic sleeping"
else
    echo "✓ Sleep appears to be disabled"
fi

echo ""

# Check Wake for Network Access
WAKE_ON_NET=$(pmset -g | grep -c "womp.*1" || echo "0")
if [ "$WAKE_ON_NET" != "0" ]; then
    echo "✓ Wake on network access is enabled"
else
    echo "ℹ️  Wake on network access is disabled (optional for remote access)"
fi

echo ""
echo "=== Launchd Jobs Status ==="
launchctl list | grep agentic-trader
