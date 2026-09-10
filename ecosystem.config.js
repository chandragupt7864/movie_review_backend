module.exports = {
  apps: [
    {
      name: "movie-review-api",
      script: "venv/Scripts/python.exe",
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000",
      cwd: "./",
      autorestart: true,
      watch: false,
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
