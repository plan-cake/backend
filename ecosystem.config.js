const path = require('path');

module.exports = {
    apps: [
        {
            name: "plancake-site",
            cwd: path.join(__dirname, '../frontend'),
            script: "npm",
            args: "start",
            env: {
                NODE_ENV: "production",
                PORT: 3000
            },
            instances: 1,
            autorestart: true,
            max_memory_restart: "200M",
        },
        {
            name: "plancake-api",
            cwd: __dirname,
            script: "./.venv/bin/gunicorn",
            args: "api.wsgi --bind 127.0.0.1:8000",
            instances: 1,
            autorestart: true,
            max_memory_restart: "150M",
        },
        {
            name: "celery-worker",
            cwd: __dirname,
            script: "./.venv/bin/celery",
            args: "-A api worker -loglevel=info",
            instances: 1,
            autorestart: true,
            max_memory_restart: "150M",
        },
        {
            name: "celery-beat",
            cwd: __dirname,
            script: "./.venv/bin/celery",
            args: "-A api beat -loglevel=info",
            instances: 1,
            autorestart: true,
            max_memory_restart: "100M",
        },
    ]
};