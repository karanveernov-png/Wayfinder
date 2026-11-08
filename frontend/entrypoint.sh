#!/bin/sh
# Generate nginx.conf with the PORT from Cloud Run (or fallback to 80)
# Cloud Run injects PORT environment variable (default 8080)
PORT="${PORT:-80}"

cat > /etc/nginx/conf.d/default.conf <<EOF
server {
    listen ${PORT};
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF

# Start nginx in foreground
exec nginx -g "daemon off;"