#!/usr/bin/env bash
# Pair the Chromecast Voice Remote cleanly: forget any stale bond, wait for its advertisement, pair at once, trust, connect.
# Put the remote in pairing mode first (hold Back + Home until the LED blinks). Pairing as soon as it advertises avoids the
# half-finished pairings that leave mismatched keys (bluetoothd then logs "unlikely error" on every read).
# Usage: pair-remote.sh [-c controller-address] [remote-address]
#   -c   pair on this Bluetooth adapter (default: bluetoothctl's default controller)
#   remote-address defaults to the first "Chromecast Remote" seen
set -uo pipefail
ctrl=""
if [ "${1:-}" = "-c" ]; then
	ctrl="$2"
	shift 2
fi
addr="${1:-}"
timeout_s=60

coproc BT { stdbuf -oL bluetoothctl 2>&1; }
send() { echo "$1" >&"${BT[1]}"; }
if [ -n "$ctrl" ]; then
	send "select $ctrl"
fi
if [ -n "$addr" ]; then
	send "disconnect $addr"
	send "remove $addr"
	sleep 2
fi
send "agent NoInputNoOutput"
sleep 0.5
send "default-agent"
send "scan on"

echo "Waiting up to ${timeout_s}s for the remote (hold Back + Home until the LED blinks)..."
end=$((SECONDS + timeout_s))
state=wait
result=""
while [ $SECONDS -lt $end ]; do
	IFS= read -t 2 -r line <&"${BT[0]}" || continue
	l=$(sed 's/\x1b\[[0-9;]*m//g' <<<"$line")
	if [ $state = wait ]; then
		if [ -z "$addr" ] && grep -qE "(NEW|CHG).*Device ([0-9A-F:]{17}) Chromecast Remote" <<<"$l"; then
			addr=$(grep -oE "[0-9A-F]{2}(:[0-9A-F]{2}){5}" <<<"$l" | head -1)
		fi
		if [ -n "$addr" ] && grep -qE "(NEW|CHG).*$addr" <<<"$l"; then
			echo "Seen $addr, pairing"
			send "pair $addr"
			state=pairing
		fi
	fi
	if grep -qE "Pairing successful|Failed to pair" <<<"$l"; then
		result=$(grep -oE "Pairing successful|Failed to pair.*" <<<"$l")
		break
	fi
done
echo "${result:-Timed out without seeing the remote}"
if [ -n "$addr" ]; then
	send "trust $addr"
	sleep 1
	send "connect $addr"
	sleep 4
fi
send "scan off"
send quit
sleep 1
[ -z "$addr" ] && exit 1
# Judge by the final bond, not the pair reply: the remote sometimes cancels our request and then completes pairing itself.
sleep 3
info="$({ [ -n "$ctrl" ] && echo "select $ctrl"; echo "info $addr"; sleep 1; echo quit; } | bluetoothctl 2>&1 | sed 's/\x1b\[[0-9;]*m//g')"
grep -E "Name|Paired|Bonded|Trusted|Connected" <<<"$info"
grep -q "Bonded: yes" <<<"$info"
