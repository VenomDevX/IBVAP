#!/usr/bin/env python3
"""
IBVAP — TensorRT Engine Export Script

Exports a YOLO .pt model to a TensorRT .engine file for maximum GPU inference
throughput. The resulting engine is hardware-specific (tied to the exact GPU
architecture and TensorRT version).

Two-stage pipeline:
  1. If no ONNX exists, use Ultralytics to export .pt → .onnx
  2. Build .onnx → .engine directly via TensorRT Python API
     (bypasses Ultralytics' TensorRT export, which requires nvidia-modelopt)

Usage:
    python scripts/export_tensorrt.py --weights models/ibvap_coarse.pt --half --imgsz 640

The engine file is written alongside the source weights:
    models/ibvap_coarse.pt  →  models/ibvap_coarse.engine
"""

import argparse
import sys
import time
from pathlib import Path


def build_engine_from_onnx(
    onnx_path: Path,
    engine_path: Path,
    use_half: bool = True,
    workspace_gb: int = 4,
    verbose: bool = False,
) -> Path:
    """Build a TensorRT engine directly from an ONNX file."""
    import tensorrt as trt

    TRT_LOGGER = trt.Logger(trt.Logger.VERBOSE if verbose else trt.Logger.WARNING)

    print(f"  Building TensorRT engine from: {onnx_path}")
    print(f"  Target: {engine_path}")
    print(f"  Precision: {'FP16' if use_half else 'FP32'}")

    builder = trt.Builder(TRT_LOGGER)
    # TensorRT 10+ defaults to explicit batch; the flag was removed in 11.x.
    try:
        flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    except AttributeError:
        flag = 0  # TRT 11+: explicit batch is always on
    network = builder.create_network(flag)
    parser = trt.OnnxParser(network, TRT_LOGGER)

    # Parse ONNX
    with open(onnx_path, "rb") as f:
        if not parser.parse(f.read()):
            for i in range(parser.num_errors):
                print(f"  ONNX parse error: {parser.get_error(i)}")
            raise RuntimeError("Failed to parse ONNX model")

    print(f"  ONNX parsed: {network.num_layers} layers, {network.num_inputs} inputs, {network.num_outputs} outputs")

    # Configure builder
    config = builder.create_builder_config()
    try:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_gb * (1 << 30))
    except (AttributeError, TypeError):
        config.max_workspace_size = workspace_gb * (1 << 30)

    if use_half:
        # TRT 11 removed BuilderFlag.FP16 and per-layer precision.
        # Try legacy flag first; if unavailable, TRT 11 auto-selects
        # optimal precision per kernel from the ONNX model (which was
        # exported with FP16 weights). Enable TF32 for Tensor Core usage.
        try:
            config.set_flag(trt.BuilderFlag.FP16)
            print("  FP16 enabled (via BuilderFlag)")
        except AttributeError:
            print("  TRT 11+: auto-precision from FP16 ONNX weights")
        # TF32 uses Tensor Cores for FP32 ops — always beneficial on RTX 40
        try:
            config.set_flag(trt.BuilderFlag.TF32)
            print("  TF32 Tensor Core acceleration enabled")
        except AttributeError:
            pass

    # Build engine
    print("  Building engine (this takes a few minutes)...")
    start = time.perf_counter()

    serialized_engine = builder.build_serialized_network(network, config)
    if serialized_engine is None:
        raise RuntimeError("TensorRT engine build failed")

    elapsed = time.perf_counter() - start
    print(f"  Engine built in {elapsed:.1f}s")

    # Save
    with open(engine_path, "wb") as f:
        f.write(serialized_engine)

    size_mb = engine_path.stat().st_size / (1024 * 1024)
    print(f"  Saved: {engine_path} ({size_mb:.1f} MB)")
    return engine_path


def main():
    parser = argparse.ArgumentParser(
        description="Export a YOLO model to TensorRT engine"
    )
    parser.add_argument(
        "--weights",
        type=str,
        required=True,
        help="Path to the .pt model file (e.g. models/ibvap_coarse.pt)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image size for the engine (default: 640)",
    )
    parser.add_argument(
        "--half",
        action="store_true",
        default=True,
        help="Export with FP16 half precision (default: True)",
    )
    parser.add_argument(
        "--no-half",
        action="store_true",
        help="Export with FP32 full precision",
    )
    parser.add_argument(
        "--workspace",
        type=int,
        default=4,
        help="TensorRT builder workspace in GB (default: 4)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose export logging",
    )
    args = parser.parse_args()

    use_half = args.half and not args.no_half

    weights_path = Path(args.weights)
    if not weights_path.exists():
        print(f"ERROR: Weights file not found: {weights_path}")
        sys.exit(1)

    onnx_path = weights_path.with_suffix(".onnx")
    engine_path = weights_path.with_suffix(".engine")

    print("=" * 60)
    print("  IBVAP — TensorRT Engine Export")
    print("=" * 60)
    print(f"  Source:     {weights_path}")
    print(f"  ONNX:       {onnx_path}")
    print(f"  Engine:     {engine_path}")
    print(f"  Precision:  {'FP16 (half)' if use_half else 'FP32 (full)'}")
    print(f"  Image size: {args.imgsz}")
    print(f"  Workspace:  {args.workspace} GB")
    print("=" * 60)

    # --- Check CUDA ---
    try:
        import torch
        if not torch.cuda.is_available():
            print("ERROR: CUDA is not available.")
            sys.exit(1)
        print(f"\n  GPU: {torch.cuda.get_device_name(0)}")
        print(f"  CUDA: {torch.version.cuda}")
    except ImportError:
        print("ERROR: PyTorch not installed.")
        sys.exit(1)

    # --- Check TensorRT ---
    try:
        import tensorrt as trt
        print(f"  TensorRT: {trt.__version__}")
    except ImportError:
        print("ERROR: tensorrt not installed.")
        sys.exit(1)

    # --- Stage 1: .pt → .onnx (skip if ONNX already exists) ---
    if onnx_path.exists():
        print(f"\n  ONNX already exists: {onnx_path} ({onnx_path.stat().st_size / 1024 / 1024:.1f} MB)")
        print("  Skipping ONNX export (delete to re-export)")
    else:
        print(f"\nStage 1: Exporting {weights_path} → ONNX ...")
        try:
            from ultralytics import YOLO
            model = YOLO(str(weights_path))
            model.export(format="onnx", imgsz=args.imgsz, half=use_half, simplify=True)
            if not onnx_path.exists():
                print(f"ERROR: ONNX export did not produce {onnx_path}")
                sys.exit(1)
            print(f"  ONNX created: {onnx_path} ({onnx_path.stat().st_size / 1024 / 1024:.1f} MB)")
        except Exception as e:
            print(f"ERROR: ONNX export failed: {e}")
            sys.exit(1)

    # --- Stage 2: .onnx → .engine (direct TensorRT API) ---
    print(f"\nStage 2: Building TensorRT engine ...")
    try:
        build_engine_from_onnx(
            onnx_path=onnx_path,
            engine_path=engine_path,
            use_half=use_half,
            workspace_gb=args.workspace,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"ERROR: Engine build failed: {e}")
        sys.exit(1)

    # --- Validate ---
    print("\nValidating engine loads correctly ...")
    try:
        from ultralytics import YOLO
        engine_model = YOLO(str(engine_path))
        import numpy as np
        dummy = np.zeros((args.imgsz, args.imgsz, 3), dtype=np.uint8)
        engine_model(dummy, verbose=False)
        print("  ✓ Engine loads and runs via Ultralytics YOLO()")
    except Exception as e:
        # Even if Ultralytics can't load it, TensorRT runtime can
        print(f"  ⚠ Ultralytics validation: {e}")
        print("  Trying direct TensorRT runtime validation ...")
        try:
            runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
            with open(engine_path, "rb") as f:
                engine = runtime.deserialize_cuda_engine(f.read())
            if engine is not None:
                print(f"  ✓ Engine deserializes correctly ({engine.num_io_tensors} I/O tensors)")
            else:
                print("  ✗ Engine deserialization failed")
                sys.exit(1)
        except Exception as e2:
            print(f"  ✗ Direct validation also failed: {e2}")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("  Export complete!")
    print(f"  Engine: {engine_path}")
    print("  The pipeline will auto-discover this on next startup.")
    print("=" * 60)


if __name__ == "__main__":
    main()
