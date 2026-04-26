#!/bin/bash
# WireGuard setup for secure Pi ↔ Backend communication

set -e

# Configuration
PI_HOSTNAME=${1:-raspberrypi}
BACKEND_HOST=${2:-192.168.1.100}
BACKEND_PORT=${3:-51820}
WG_SUBNET=${4:-10.0.0.0/24}

PI_WG_IP=$(echo "$WG_SUBNET" | sed 's/0\/24/2/')
BACKEND_WG_IP=$(echo "$WG_SUBNET" | sed 's/0\/24/1/')

echo "Setting up WireGuard tunnel"
echo "  Pi hostname: $PI_HOSTNAME"
echo "  Backend host: $BACKEND_HOST"
echo "  WireGuard subnet: $WG_SUBNET"
echo "  Pi WireGuard IP: $PI_WG_IP"
echo "  Backend WireGuard IP: $BACKEND_WG_IP"

# Install WireGuard
echo "Installing WireGuard..."
sudo apt-get update
sudo apt-get install -y wireguard wireguard-tools

# Create keys
echo "Generating WireGuard keys..."
sudo mkdir -p /etc/wireguard
cd /tmp
umask 077
wg genkey | tee pi_private.key | wg pubkey > pi_public.key
wg genkey | tee backend_private.key | wg pubkey > backend_public.key

echo "Pi public key:"
cat pi_public.key
echo ""
echo "Backend public key:"
cat backend_public.key
echo ""

# Create Pi WireGuard config
echo "Creating Pi WireGuard configuration..."
sudo tee /etc/wireguard/wg0.conf > /dev/null << EOF
[Interface]
Address = $PI_WG_IP/32
PrivateKey = $(cat pi_private.key)
ListenPort = 51820

[Peer]
PublicKey = $(cat backend_public.key)
Endpoint = $BACKEND_HOST:$BACKEND_PORT
AllowedIPs = $BACKEND_WG_IP/32
PersistentKeepalive = 25
EOF

# Generate Backend WireGuard config (print for manual setup)
echo ""
echo "=== Backend WireGuard Configuration (set up on backend host) ==="
cat << EOF
[Interface]
Address = $BACKEND_WG_IP/32
PrivateKey = $(cat backend_private.key)
ListenPort = $BACKEND_PORT

[Peer]
PublicKey = $(cat pi_public.key)
AllowedIPs = $PI_WG_IP/32
PersistentKeepalive = 25
EOF
echo "=== End Backend Configuration ==="
echo ""

# Enable WireGuard
echo "Enabling WireGuard..."
sudo chmod 600 /etc/wireguard/wg0.conf
sudo wg-quick up wg0

# Add to system startup
echo "Adding WireGuard to systemd..."
sudo systemctl enable wg-quick@wg0

# Test connection
echo ""
echo "Testing WireGuard connection (you may need to setup backend first)..."
sleep 2
ping -c 1 $BACKEND_WG_IP || echo "Backend not yet responding (expected if not set up yet)"

echo ""
echo "WireGuard setup complete!"
echo ""
echo "Next steps:"
echo "1. Set up WireGuard on backend with the config above"
echo "2. Test connection: ping $BACKEND_WG_IP"
echo "3. Update edge/main.py to use WireGuard tunnel URL"
echo ""
echo "To disable WireGuard: sudo wg-quick down wg0"
