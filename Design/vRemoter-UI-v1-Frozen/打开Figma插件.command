#!/bin/zsh
set -e
open -a "Figma"
open "$(dirname "$0")"
open -a "TextEdit" "$(dirname "$0")/README.md"
