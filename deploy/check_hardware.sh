#!/bin/bash
# Check Raspberry Pi hardware prerequisites

echo "=== Multi-Persona Voice Agent - Hardware Check ==="
echo ""

ERRORS=0
WARNINGS=0

# Check OS
echo "[*] Checking OS..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "    OS: $NAME ($VERSION_ID)"
    if [[ "$VERSION_ID" != "11" && "$VERSION_ID" != "12" ]]; then
        echo "    WARNING: Recommended Raspberry Pi OS 11 or 12, got $VERSION_ID"
        ((WARNINGS++))
    fi
else
    echo "    ERROR: Not running Raspberry Pi OS"
    ((ERRORS++))
fi
echo ""

# Check CPU
echo "[*] Checking CPU..."
if [ -f /proc/cpuinfo ]; then
    MODEL=$(grep "Model" /proc/cpuinfo | head -1)
    echo "    $MODEL"
    if ! grep -q "BCM2711" /proc/cpuinfo; then
        echo "    WARNING: Not Raspberry Pi 4B (BCM2711)"
        ((WARNINGS++))
    fi
fi
echo ""

# Check RAM
echo "[*] Checking RAM..."
TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
TOTAL_GB=$((TOTAL_KB / 1024 / 1024))
echo "    Total RAM: ${TOTAL_GB}GB"
if [ "$TOTAL_GB" -lt 4 ]; then
    echo "    WARNING: Recommend 4GB+ RAM, you have ${TOTAL_GB}GB"
    ((WARNINGS++))
fi
echo ""

# Check camera
echo "[*] Checking Camera..."
if vcgencmd get_camera | grep -q "supported=1"; then
    if vcgencmd get_camera | grep -q "detected=1"; then
        echo "    Camera: DETECTED"
    else
        echo "    WARNING: Camera not detected (may need to enable in raspi-config)"
        ((WARNINGS++))
    fi
else
    echo "    ERROR: Camera not supported"
    ((ERRORS++))
fi
echo ""

# Check audio
echo "[*] Checking Audio..."
if aplay -l 2>/dev/null | grep -q "card"; then
    echo "    Playback: OK"
else
    echo "    WARNING: No audio output devices found"
    ((WARNINGS++))
fi
if arecord -l 2>/dev/null | grep -q "card"; then
    echo "    Recording: OK"
else
    echo "    WARNING: No audio input devices found"
    ((WARNINGS++))
fi
echo ""

# Check Python
echo "[*] Checking Python..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "    Python: $PYTHON_VERSION"
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 9 ]); then
    echo "    ERROR: Python 3.9+ required"
    ((ERRORS++))
fi
echo ""

# Check pip packages
echo "[*] Checking Python packages..."
REQUIRED_PACKAGES=(
    "pydantic"
    "PyYAML"
)
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import ${pkg,,}" 2>/dev/null; then
        echo "    ✓ $pkg"
    else
        echo "    ✗ $pkg (missing)"
        ((ERRORS++))
    fi
done
echo ""

# Check optional hardware packages
echo "[*] Checking optional hardware libraries..."
OPTIONAL_PACKAGES=(
    "picamera2:Camera"
    "openwakeword:Wake word"
    "insightface:Face recognition"
    "sherpa_onnx:Speech recognition"
)
for entry in "${OPTIONAL_PACKAGES[@]}"; do
    pkg="${entry%%:*}"
    name="${entry##*:}"
    if python3 -c "import ${pkg}" 2>/dev/null; then
        echo "    ✓ $name ($pkg)"
    else
        echo "    ○ $name ($pkg) - optional, will need setup"
    fi
done
echo ""

# Check storage
echo "[*] Checking storage..."
AVAILABLE_GB=$(df /home | tail -1 | awk '{printf "%.1f", $4/1024/1024}')
echo "    Available space: ${AVAILABLE_GB}GB"
if (( $(echo "$AVAILABLE_GB < 10" | bc -l) )); then
    echo "    WARNING: Recommend 10GB+ free space, you have ${AVAILABLE_GB}GB"
    ((WARNINGS++))
fi
echo ""

# Check GPIO
echo "[*] Checking GPIO access..."
if [ -w /dev/gpiomem ]; then
    echo "    GPIO: Accessible"
elif sudo -n true 2>/dev/null; then
    echo "    GPIO: Accessible with sudo"
else
    echo "    WARNING: GPIO may need sudo or user in gpio group"
    ((WARNINGS++))
fi
echo ""

# Summary
echo "========================================="
echo "SUMMARY"
echo "========================================="
echo "Errors:   $ERRORS"
echo "Warnings: $WARNINGS"
echo ""

if [ $ERRORS -eq 0 ]; then
    echo "✓ Hardware prerequisites OK"
    if [ $WARNINGS -gt 0 ]; then
        echo "⚠ Review warnings above"
    fi
    exit 0
else
    echo "✗ Hardware check failed"
    exit 1
fi
