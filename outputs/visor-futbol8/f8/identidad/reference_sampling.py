"""Retain readable jersey crops at diverse distances and independent instants."""
from collections import defaultdict
OCR_REFERENCE_LIMIT=24

def distance_bucket(height):
    return 'far' if height<80 else 'medium' if height<140 else 'near'

def retain_ocr_candidates(candidates,limit=OCR_REFERENCE_LIMIT):
    grouped=defaultdict(list)
    for c in candidates:grouped[distance_bucket(c.get('height',100))].append(c)
    kept=[];names=set()
    def independent(c):
        return c['file'] not in names and not any('time' in c and 'time' in k and abs(c['time']-k['time'])<.55 for k in kept)
    def take(pool,count):
        for c in sorted(pool,key=lambda c:(c['quality'],-c['frame']),reverse=True):
            if count<=0:break
            if independent(c):kept.append(c);names.add(c['file']);count-=1
    for key in ('far','medium','near'):take(grouped[key],limit//3)
    take(candidates,max(0,limit-len(kept)))
    return sorted(kept,key=lambda c:c['frame'])
