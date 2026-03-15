# Remote Spawn Options for ComfyUI Server Mode

## Overview

ComfyUI can run in server (headless) mode, exposing an API that allows remote clients to queue prompts, upload images, and control workflow execution. This document covers the spawn options available when launching ComfyUI in server mode and how to interact with it remotely.

## Server Mode Spawn Options

### Basic Launch

```bash
python main.py --listen 0.0.0.0 --port 8188
```

### Full Option Reference

| Option | Default | Description |
|---|---|---|
| `--listen [ADDRESS]` | `127.0.0.1` | IP address to listen on. Use `0.0.0.0` to accept remote connections. |
| `--port PORT` | `8188` | Port number for the HTTP/WebSocket server. |
| `--enable-cors-header [ORIGIN]` | disabled | Enable CORS headers. Optionally restrict to a specific origin. |
| `--preview-method [METHOD]` | `none` | Preview method: `none`, `auto`, `latent2rgb`, `taesd`. |
| `--output-directory PATH` | `output/` | Directory for generated output files. |
| `--input-directory PATH` | `input/` | Directory for uploaded input files. |
| `--temp-directory PATH` | system temp | Directory for temporary files. |
| `--auto-launch` | disabled | Automatically open the browser UI on start. |
| `--disable-auto-launch` | — | Prevent auto-launching the browser. |
| `--dont-print-server` | — | Suppress server request logging. |
| `--multi-user` | disabled | Enable multi-user mode with separate queues. |

### GPU and Performance Options

| Option | Default | Description |
|---|---|---|
| `--cuda-device DEVICE_ID` | `0` | CUDA device index to use. |
| `--gpu-only` | disabled | Run everything on the GPU (higher VRAM usage). |
| `--highvram` | disabled | Keep models in GPU VRAM instead of offloading. |
| `--normalvram` | disabled | Default VRAM management. |
| `--lowvram` | disabled | Aggressive VRAM optimization for low-memory GPUs. |
| `--novram` | disabled | Minimal VRAM usage, offload almost everything to CPU. |
| `--cpu` | disabled | Run entirely on CPU. |
| `--fp16-vae` | disabled | Use FP16 precision for VAE. |
| `--bf16-vae` | disabled | Use BF16 precision for VAE. |
| `--fp32-vae` | disabled | Force FP32 precision for VAE. |
| `--disable-xformers` | disabled | Disable xformers memory-efficient attention. |

### Queue and Execution Options

| Option | Default | Description |
|---|---|---|
| `--dont-upcast-attention` | disabled | Disable attention upcasting. |
| `--force-fp16` | disabled | Force FP16 precision for all operations. |
| `--force-fp32` | disabled | Force FP32 precision for all operations. |
| `--disable-smart-memory` | disabled | Disable smart memory management. |
| `--max-upload-size MAX_MB` | `100` | Maximum upload file size in megabytes. |

## Remote API Usage

### Queue a Prompt

```bash
curl -X POST http://<SERVER>:8188/prompt \
  -H "Content-Type: application/json" \
  -d @prompt_payload.json
```

Payload structure:

```json
{
  "prompt": { ... },
  "client_id": "unique-client-id"
}
```

### Upload an Image

```bash
curl -X POST http://<SERVER>:8188/upload/image \
  -F "image=@myimage.png"
```

### Get Queue Status

```bash
curl http://<SERVER>:8188/queue
```

### Get History

```bash
curl http://<SERVER>:8188/history
```

### Cancel Current Job

```bash
curl -X POST http://<SERVER>:8188/interrupt
```

### Clear Queue

```bash
curl -X POST http://<SERVER>:8188/queue \
  -H "Content-Type: application/json" \
  -d '{"clear": true}'
```

### Delete a Queued Item

```bash
curl -X POST http://<SERVER>:8188/queue \
  -H "Content-Type: application/json" \
  -d '{"delete": ["PROMPT_ID"]}'
```

## WebSocket Connection for Real-Time Updates

Connect to `ws://<SERVER>:8188/ws?clientId=<CLIENT_ID>` to receive:

- `status` — Queue status changes
- `execution_start` — Workflow execution begins
- `executing` — Currently executing node (includes node ID)
- `progress` — Step progress within a node (step/total)
- `executed` — Node finished with output data
- `execution_cached` — Nodes skipped due to caching
- `execution_error` — Error during execution

### Example (Python)

```python
import websocket
import json
import urllib.request

SERVER = "127.0.0.1:8188"
CLIENT_ID = "my-remote-client"

def queue_prompt(prompt):
    payload = json.dumps({"prompt": prompt, "client_id": CLIENT_ID}).encode("utf-8")
    req = urllib.request.Request(f"http://{SERVER}/prompt", data=payload)
    req.add_header("Content-Type", "application/json")
    return json.loads(urllib.request.urlopen(req).read())

def listen():
    ws = websocket.WebSocket()
    ws.connect(f"ws://{SERVER}/ws?clientId={CLIENT_ID}")
    while True:
        msg = ws.recv()
        if isinstance(msg, str):
            data = json.loads(msg)
            print(data["type"], data.get("data", {}).get("node"))
```

## Spawning with Docker

```bash
docker run -d \
  --gpus all \
  -p 8188:8188 \
  -v $(pwd)/models:/comfyui/models \
  -v $(pwd)/output:/comfyui/output \
  -v $(pwd)/input:/comfyui/input \
  comfyui:latest \
  --listen 0.0.0.0 --port 8188
```

## Spawning Behind a Reverse Proxy

When exposing ComfyUI remotely, use a reverse proxy with authentication:

```nginx
server {
    listen 443 ssl;
    server_name comfyui.example.com;

    ssl_certificate     /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8188;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

## Loading This Workflow Remotely

To queue the AnimateDiff workflow from this repository:

```bash
curl -X POST http://<SERVER>:8188/prompt \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": $(cat workflow.json | python3 -c 'import sys,json; w=json.load(sys.stdin); print(json.dumps({str(n[\"id\"]): {\"class_type\": n[\"type\"], \"inputs\": dict(zip([i.get(\"name\",f\"input_{j}\") for j,i in enumerate(n.get(\"inputs\",[]))], n.get(\"widgets_values\",[])))} for n in w[\"nodes\"]}))')}"
```

For a cleaner approach, use the [ComfyUI API format](https://github.com/comfyanonymous/ComfyUI) to convert the workflow to an API-compatible prompt payload.
