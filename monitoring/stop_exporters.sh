#!/usr/bin/env bash
for sw in sw1 sw2 sw3; do
  docker rm -f "ne-$sw" >/dev/null 2>&1 && echo "removed ne-$sw"
done
