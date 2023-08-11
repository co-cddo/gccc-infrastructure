#!/usr/bin/env bash

rm ./*.zip || echo "No ZIPs to delete"
rm -rf .target || echo "No .target/ to delete"
mkdir .target

python3.11 -m pip install -r requirements.txt -t .target/ --upgrade --no-user

cp ./*.py .target/

cd .target/ || exit 1

find . -type f -exec chmod 0644 {} \;
find . -type d -exec chmod 0755 {} \;

zip -r ../target.zip .

cd ../
