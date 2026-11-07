module.exports = {
  apps: [
    {
      name: "cmms_app",
      script: "gunicorn",
      args: "-w 4 -k gevent -b 0.0.0.0:5002 \"app:create_app()\"",
      interpreter: "python",
      cwd: "/home/cmms_app",
      env: {
        FLASK_ENV: "production",
      },
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      out_file: "/home/cmms_app/logs/app.out.log",
      err_file: "/home/cmms_app/logs/app.err.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
