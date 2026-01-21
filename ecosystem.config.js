const path = require('path');

module.exports = {
    apps: [
        {
            name: "plancake-api",
            cwd: __dirname,
            script: "./.venv/bin/python",
            args: "-m gunicorn api.wsgi --bind 127.0.0.1:8000",
            instances: 1,
            autorestart: true,
            max_memory_restart: "150M",
        },
        {
            name: "celery-worker",
            cwd: __dirname,
            script: "./.venv/bin/python",
            args: "-m celery -A api worker --loglevel=info",
            instances: 1,
            autorestart: true,
            max_memory_restart: "150M",
        },
        {
            name: "celery-beat",
            cwd: __dirname,
            script: "./.venv/bin/python",
            args: "-m celery -A api beat --loglevel=info",
            instances: 1,
            autorestart: true,
            max_memory_restart: "100M",
        },
    ]
};