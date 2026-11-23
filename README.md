# Noisy Cell Counter

Upload microscopy images, review detected cells, correct the count, and inspect an uncertainty estimate based on how cells are distributed across image tiles.

## Run the app

From this folder, run:

```bash
./start.sh
```

The script creates a local Python environment on first launch, installs the backend dependencies, starts the Flask service, and serves the frontend at <http://127.0.0.1:8000>. Press Ctrl+C in the terminal to stop it.

You can also start the service manually after installing `backend/requirements.txt`:

```bash
python3 backend/app.py
```
git add -A
git commit -m "Describe your changes"
git push
