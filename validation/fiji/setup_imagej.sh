#!/usr/bin/env bash
# Build a minimal ImageJ 1.53t installation with the Fast4DReg/NanoJ plugin.
# Usage: setup_imagej.sh TARGET_DIR FAST4DREG_REPO_DIR
# Requires: curl, javac, jar (JDK 11+).
set -euo pipefail
TARGET=$1
REPO=$2
M=https://repo1.maven.org/maven2
mkdir -p "$TARGET/plugins"
curl -sSf --retry 5 --retry-all-errors --retry-delay 5 -o "$TARGET/ij.jar" "$M/net/imagej/ij/1.53t/ij-1.53t.jar"
for p in com/github/wendykierp/JTransforms/3.1/JTransforms-3.1.jar \
         pl/edu/icm/JLargeArrays/1.5/JLargeArrays-1.5.jar \
         org/apache/commons/commons-math3/3.5/commons-math3-3.5.jar \
         org/apache/commons/commons-compress/1.21/commons-compress-1.21.jar; do
  curl -sSf --retry 5 --retry-all-errors --retry-delay 5 -o "$TARGET/plugins/$(basename "$p")" "$M/$p"
done
SRC="$REPO/Fast4DReg/jar-files/src/main"
CLASSES=$(mktemp -d)
javac -nowarn -d "$CLASSES" -cp "$TARGET/ij.jar:$TARGET/plugins/*" \
  $(find "$SRC/java" -name '*.java')
cp "$SRC/resources/plugins.config" "$CLASSES/"
jar cf "$TARGET/plugins/Fast4DReg_.jar" -C "$CLASSES" .
rm -rf "$CLASSES"
sha256sum "$TARGET/ij.jar" "$TARGET/plugins/"*.jar
