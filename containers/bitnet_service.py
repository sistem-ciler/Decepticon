#!/usr/bin/env python3
"""
BitNet Inference Service Wrapper
Provides a clean API for integrating BitNet into the Decepticon stack.
"""
import os
import sys
import json
import subprocess
import logging
import time
import signal
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BitNet] %(levelname)s: %(message)s")
logger = logging.getLogger("bitnet-service")

BITNET_DIR = Path("/opt/bitnet")
MODEL_DIR = BITNET_DIR / "models"
BUILD_DIR = BITNET_DIR / "build"
SERVER_BINARY = BUILD_DIR / "bin" / "llama-server"

SUPPORTED_MODELS = {
    "bitnet-2b": {
        "hf_repo": "microsoft/BitNet-b1.58-2B-4T",
        "model_name": "BitNet-b1.58-2B-4T",
        "params": "2.4B",
        "ram_gb": 1.5,
        "description": "Best quality/speed ratio for general tasks"
    },
    "bitnet-3b": {
        "hf_repo": "1bitLLM/bitnet_b1_58-3B",
        "model_name": "bitnet_b1_58-3B",
        "params": "3.3B",
        "ram_gb": 2.5,
        "description": "Larger model for complex tasks"
    },
    "llama3-8b-bitnet": {
        "hf_repo": "HF1BitLLM/Llama3-8B-1.58-100B-tokens",
        "model_name": "Llama3-8B-1.58-100B-tokens",
        "params": "8.0B",
        "ram_gb": 5.0,
        "description": "Highest quality 1-bit model"
    },
    "falcon3-1b": {
        "hf_repo": "tiiuae/Falcon3-1B-Instruct-1.58bit",
        "model_name": "Falcon3-1B-Instruct-1.58bit",
        "params": "1.0B",
        "ram_gb": 1.0,
        "description": "Smallest model, fastest inference"
    },
    "falcon3-3b": {
        "hf_repo": "tiiuae/Falcon3-3B-Instruct-1.58bit",
        "model_name": "Falcon3-3B-Instruct-1.58bit",
        "params": "3.0B",
        "ram_gb": 2.0,
        "description": "Good multilingual support"
    },
    "falcon-e-1b": {
        "hf_repo": "tiiuae/Falcon-E-1B-Instruct",
        "model_name": "Falcon-E-1B-Instruct",
        "params": "1.0B",
        "ram_gb": 0.8,
        "description": "Edge-optimized model"
    },
    "falcon-e-3b": {
        "hf_repo": "tiiuae/Falcon-E-3B-Instruct",
        "model_name": "Falcon-E-3B-Instruct",
        "params": "3.0B",
        "ram_gb": 1.5,
        "description": "Edge-optimized, better quality"
    }
}


def get_model_path(model_id: str, quant_type: str = "i2_s") -> Optional[Path]:
    """Get the path to a quantized model file."""
    if model_id not in SUPPORTED_MODELS:
        return None
    model_info = SUPPORTED_MODELS[model_id]
    model_dir = MODEL_DIR / model_info["model_name"]
    gguf_path = model_dir / f"ggml-model-{quant_type}.gguf"
    if gguf_path.exists():
        return gguf_path
    # Try alternative quant types
    for qt in ["i2_s", "tl1", "tl2"]:
        alt_path = model_dir / f"ggml-model-{qt}.gguf"
        if alt_path.exists():
            return alt_path
    return None


def list_available_models() -> list:
    """List models that are already downloaded and quantized."""
    available = []
    for model_id, info in SUPPORTED_MODELS.items():
        model_path = get_model_path(model_id)
        if model_path:
            available.append({
                "id": model_id,
                "params": info["params"],
                "ram_gb": info["ram_gb"],
                "path": str(model_path),
                "description": info["description"]
            })
    return available


def start_server(model_id: str = "bitnet-2b", host: str = "0.0.0.0", port: int = 8080,
                 ctx_size: int = 4096, threads: int = None, quant_type: str = "i2_s"):
    """Start the BitNet llama-server."""
    if threads is None:
        threads = max(1, os.cpu_count() - 1)

    model_path = get_model_path(model_id, quant_type)
    if not model_path:
        logger.error(f"Model {model_id} not found. Run setup first.")
        sys.exit(1)

    if not SERVER_BINARY.exists():
        logger.error(f"Server binary not found at {SERVER_BINARY}. Build BitNet first.")
        sys.exit(1)

    cmd = [
        str(SERVER_BINARY),
        "-m", str(model_path),
        "-c", str(ctx_size),
        "-t", str(threads),
        "-n", "2048",
        "-ngl", "0",
        "--temp", "0.8",
        "--host", host,
        "--port", str(port),
        "-cb"  # continuous batching
    ]

    logger.info(f"Starting BitNet server: model={model_id}, host={host}:{port}, threads={threads}")
    logger.info(f"Model path: {model_path}")

    # Start the server process
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BITNET_DIR)
    )

    logger.info(f"BitNet server started (PID {process.pid})")
    logger.info(f"API endpoint: http://{host}:{port}/v1")
    logger.info(f"Health check: http://{host}:{port}/health")

    # Stream output
    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                logger.info(f"[llama-server] {line}")
    except KeyboardInterrupt:
        logger.info("Shutting down BitNet server...")
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()

    return process.returncode


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="BitNet Inference Service")
    parser.add_argument("--model", default="bitnet-2b", choices=SUPPORTED_MODELS.keys())
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--quant-type", default="i2_s", choices=["i2_s", "tl1", "tl2"])
    parser.add_argument("--list-models", action="store_true", help="List available models")

    args = parser.parse_args()

    if args.list_models:
        available = list_available_models()
        if available:
            print("\nAvailable models:")
            for m in available:
                print(f"  {m['id']:20s} {m['params']:8s} {m['ram_gb']}GB RAM  {m['description']}")
        else:
            print("\nNo models available. Run setup to download and quantize models.")
            print("\nSupported models:")
            for mid, info in SUPPORTED_MODELS.items():
                print(f"  {mid:20s} {info['params']:8s} {info['ram_gb']}GB RAM  {info['description']}")
    else:
        sys.exit(start_server(
            model_id=args.model,
            host=args.host,
            port=args.port,
            ctx_size=args.ctx_size,
            threads=args.threads,
            quant_type=args.quant_type
        ))
