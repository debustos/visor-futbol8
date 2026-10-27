"""Shared JSON and ONNX helpers and box geometry used by every module. Moved from automatic_core.py without changes."""
from __future__ import annotations
import json
from pathlib import Path

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');temp.replace(path)

def ort_session(path,gpu=True):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.enable_mem_pattern=False;options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    providers=['DmlExecutionProvider','CPUExecutionProvider'] if gpu and 'DmlExecutionProvider' in ort.get_available_providers() else ['CPUExecutionProvider']
    return ort.InferenceSession(str(path),options,providers=providers)

def crop(img,box,a=0,b=1,c=0,d=1):
    x1,y1,x2,y2=box;h=y2-y1;w=x2-x1
    return img[max(0,round(y1+a*h)):min(img.shape[0],round(y1+b*h)),max(0,round(x1+c*w)):min(img.shape[1],round(x1+d*w))]

def iou(a,b):
    left=max(a[0],b[0]);top=max(a[1],b[1]);right=min(a[2],b[2]);bottom=min(a[3],b[3]);intersection=max(0,right-left)*max(0,bottom-top)
    return intersection/max((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection,1)
