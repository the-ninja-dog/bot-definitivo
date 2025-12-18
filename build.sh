#!/bin/bash
set -e

# Instalar Flutter
export FLUTTER_VERSION=3.19.6
curl -O https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz
mkdir -p /opt/flutter
sudo tar xf flutter_linux_${FLUTTER_VERSION}-stable.tar.xz -C /opt/flutter
export PATH="/opt/flutter/flutter/bin:$PATH"
flutter --version

# Build Flutter web
flutter pub get
flutter build web --release
