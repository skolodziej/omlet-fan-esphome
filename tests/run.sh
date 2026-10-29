#!/usr/bin/env bash
# Generate the C++ for omlet-fan.yaml, pull out the omlet_evaluate lambda and
# run it against tests/logic_test.cpp on the host. Needs esphome and g++.
set -euo pipefail
cd "$(dirname "$0")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/test.yaml" <<YAML
esphome:
  name: coop-fan
packages:
  omlet: !include $PWD/../omlet-fan.yaml
api:
ota:
  - platform: esphome
wifi:
  ssid: test
  password: testtesttest
YAML
esphome compile --only-generate "$work/test.yaml" >/dev/null
main="$work/.esphome/build/coop-fan/src/main.cpp"
start=$(grep -n '      auto speed_of = \[\](select::Select \*s) -> int {' "$main" | tail -1 | cut -d: -f1)
end=$(awk -v s="$start" 'NR>s && /set_fan\(false, 0\);$/ {n=NR} NR>s && /^  \}\);/ {print n; exit}' "$main")
sed -n "${start},${end}p" "$main" > "$work/body.inc"
g++ -std=c++20 -Wall -Wno-unused -I "$work" -o "$work/logic_test" logic_test.cpp
"$work/logic_test"
