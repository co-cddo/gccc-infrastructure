#!/usr/bin/env bash
set -euo pipefail

mkdir -p .target/python/

python -V
if test -f "requirements.txt"; then
  python -m pip install -r requirements.txt -t .target/python/ --no-user
fi
if test -f "dev-requirements.txt"; then
  python -m pip install -r dev-requirements.txt
fi

cp ./*.py .target/

cd .target/ || exit 1

find . -type f -exec chmod 0644 {} \;
find . -type d -exec chmod 0755 {} \;

zip -r ../target.zip .

cd ../
