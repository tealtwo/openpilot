#!/usr/bin/env python3
import os, sys, pickle, time
import numpy as np
if "FLOAT16" not in os.environ: os.environ["FLOAT16"] = "1"
if "IMAGE" not in os.environ: os.environ["IMAGE"] = "2"
if "NOLOCALS" not in os.environ: os.environ["NOLOCALS"] = "1"
if "JIT_BATCH_SIZE" not in os.environ: os.environ["JIT_BATCH_SIZE"] = "0"

from tinygrad import Tensor, TinyJit, Context, GlobalCounters, Device, dtypes
from tinygrad.helpers import DEBUG, getenv
from tinygrad.engine.realize import CompiledRunner

import onnx
from tinygrad.frontend.onnx import OnnxRunner

if len(sys.argv) < 3:
  print("Usage: python compile_local_model.py <input.onnx> <output_tinygrad.pkl>")
  sys.exit(1)

ONNX_FILE = sys.argv[1]
OUTPUT = sys.argv[2]

def compile(onnx_file):
  run_onnx = OnnxRunner(onnx_file)
  print("loaded model")

  input_shapes = {name: spec.shape for name, spec in run_onnx.graph_inputs.items()}
  input_types = {name: spec.dtype for name, spec in run_onnx.graph_inputs.items()}
  # Float inputs and outputs to tinyjits for openpilot are always float32
  input_types = {k:(dtypes.float32 if v is dtypes.float16 else v) for k,v in input_types.items()}
  Tensor.manual_seed(100)
  new_inputs = {k:Tensor.randn(*shp, dtype=input_types[k]).mul(8).realize() for k,shp in sorted(input_shapes.items())}
  new_inputs_numpy = {k:v.numpy() for k,v in new_inputs.items()}
  print("created tensors")

  run_onnx_jit = TinyJit(lambda **kwargs:
                         next(iter(run_onnx({k:v.to(Device.DEFAULT) for k,v in kwargs.items()}).values())).cast('float32'), prune=True)
  for i in range(3):
    GlobalCounters.reset()
    print(f"run {i}")
    inputs = {**{k:v.clone() for k,v in new_inputs.items() if 'img' in k},
              **{k:Tensor(v, device="NPY").realize() for k,v in new_inputs_numpy.items() if 'img' not in k}}
    with Context(DEBUG=max(DEBUG.value, 2 if i == 2 else 1)):
      ret = run_onnx_jit(**inputs).numpy()
    # copy i == 1 so use of JITBEAM is okay
    if i == 1: test_val = np.copy(ret)
  print(f"captured {len(run_onnx_jit.captured.jit_cache)} kernels")
  np.testing.assert_equal(test_val, ret, "JIT run failed")
  print("jit run validated")

  # checks from compile2
  kernel_count = 0
  read_image_count = 0
  gated_read_image_count = 0
  for ei in run_onnx_jit.captured.jit_cache:
    if isinstance(ei.prg, CompiledRunner):
      kernel_count += 1
      read_image_count += ei.prg.p.src.count("read_image")
      gated_read_image_count += ei.prg.p.src.count("?read_image")
  print(f"{kernel_count=},  {read_image_count=}, {gated_read_image_count=}")
  if (allowed_kernel_count:=getenv("ALLOWED_KERNEL_COUNT", -1)) != -1:
    assert kernel_count == allowed_kernel_count, f"different kernels! {kernel_count=}, {allowed_kernel_count=}"
  if (allowed_read_image:=getenv("ALLOWED_READ_IMAGE", -1)) != -1:
    assert read_image_count == allowed_read_image, f"different read_image! {read_image_count=}, {allowed_read_image=}"
  if (allowed_gated_read_image:=getenv("ALLOWED_GATED_READ_IMAGE", -1)) != -1:
    assert gated_read_image_count == allowed_gated_read_image, f"different gated read_image! {gated_read_image_count=}, {allowed_gated_read_image=}"

  with open(OUTPUT, "wb") as f:
    pickle.dump(run_onnx_jit, f)
  mdl_sz = os.path.getsize(onnx_file)
  pkl_sz = os.path.getsize(OUTPUT)
  print(f"mdl size is {mdl_sz/1e6:.2f}M")
  print(f"pkl size is {pkl_sz/1e6:.2f}M")
  print("**** compile done ****")
  return test_val

if __name__ == "__main__":
  if not os.path.exists(ONNX_FILE):
    print(f"Error: {ONNX_FILE} not found")
    sys.exit(1)

  print(f"Compiling {ONNX_FILE} -> {OUTPUT}")
  compile(ONNX_FILE)