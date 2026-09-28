"""Render original, silent legal motion artwork. No stock media or contract data.
Requires Python 3, Pillow, numpy and ffmpeg. Run from the repository root.
The deterministic six-second loop is committed as a same-origin public asset.
"""
from pathlib import Path
import math
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path('frontend/public/media')
W, H, FPS, SECONDS = 960, 800, 24, 6
OUT.mkdir(parents=True, exist_ok=True)
y, x = np.mgrid[0:H, 0:W]
r = np.clip(1 - np.sqrt(((x-505)/680)**2 + ((y-300)/700)**2), 0, 1)[..., None]
base = Image.fromarray(np.uint8(np.array([12, 25, 24]) + r*np.array([16, 20, 14])), 'RGB').convert('RGBA')
base_draw = ImageDraw.Draw(base)
for size in (300, 440, 570, 720):
    base_draw.ellipse((480-size, 602-size*.25, 480+size, 602+size*.25), outline=(111, 123, 98, 28), width=1)
shadow = Image.new('RGBA', (W, H)); sd = ImageDraw.Draw(shadow)
sd.ellipse((225, 575, 775, 710), fill=(0, 0, 0, 130)); shadow = shadow.filter(ImageFilter.GaussianBlur(24))
base = Image.alpha_composite(base, shadow)

def sheet(phase: float, layer: int):
    im = Image.new('RGBA', (330, 455), (231-layer*9, 228-layer*8, 214-layer*7, 255))
    d = ImageDraw.Draw(im)
    d.rectangle((8, 8, 321, 446), outline=(178, 158, 113, 255), width=1)
    if layer:
        for yy in range(92, 375, 19): d.line((38, yy, 285, yy), fill=(174, 180, 165, 230), width=2)
        return im
    # A balanced scale, drawn geometrically rather than using a font or stock logo.
    gold = (116, 105, 72, 255)
    d.line((165, 35, 165, 80), fill=gold, width=2)
    d.line((138, 45, 192, 45), fill=gold, width=2)
    d.line((148, 80, 182, 80), fill=gold, width=2)
    for cx in (141, 189):
        d.line((cx, 45, cx-12, 65, cx+12, 65, cx, 45), fill=gold, width=1)
        d.arc((cx-12, 55, cx+12, 73), 0, 180, fill=gold, width=2)
    d.line((115, 103, 216, 103), fill=(71, 91, 81), width=5)
    d.line((143, 117, 187, 117), fill=(138, 148, 131), width=2)
    for group in range(4):
        yy = 155 + group*65
        d.rectangle((36, yy, 43, yy+7), fill=gold)
        d.line((54, yy+3, 150, yy+3), fill=(103, 115, 98), width=3)
        for row, end in enumerate((293, 277, 226)):
            d.line((36, yy+19+row*10, end, yy+19+row*10), fill=(153, 160, 140), width=2)
    d.line((39, 428, 113, 428), fill=(145, 141, 115), width=1)
    d.line((225, 428, 289, 428), fill=(145, 141, 115), width=1)
    overlay = Image.new('RGBA', im.size); od = ImageDraw.Draw(overlay)
    sy = 145 + 122*(1-math.cos(phase))
    od.rectangle((22, sy-12, 310, sy+12), fill=(188, 155, 76, 14))
    od.line((22, sy, 310, sy), fill=(145, 109, 40, 95), width=2)
    od.rounded_rectangle((26, 216, 305, 270), radius=3, outline=(172, 130, 43, 180), width=1)
    return Image.alpha_composite(im, overlay)

def project(px, py, phase, layer):
    xx, yy = px-165, py-228
    yaw, pitch, roll = math.radians(-24+3*math.sin(phase)), math.radians(12), math.radians(-12+2*math.sin(phase))
    X, Z = xx*math.cos(yaw), -xx*math.sin(yaw)
    Y, Z = yy*math.cos(pitch)-Z*math.sin(pitch), yy*math.sin(pitch)+Z*math.cos(pitch)
    X, Y = X*math.cos(roll)-Y*math.sin(roll), X*math.sin(roll)+Y*math.cos(roll)
    scale = 1.09*950/(950+Z)
    return (500+X*scale+layer*30, 380+Y*scale+layer*12+7*math.sin(phase))

def warp(im, points):
    source = [(0,0),(330,0),(330,455),(0,455)]
    A, B = [], []
    for (xx, yy), (u, v) in zip(points, source):
        A += [[xx,yy,1,0,0,0,-u*xx,-u*yy],[0,0,0,xx,yy,1,-v*xx,-v*yy]]
        B += [u,v]
    coeff = np.linalg.solve(np.asarray(A), np.asarray(B))
    return im.transform((W,H), Image.Transform.PERSPECTIVE, coeff, Image.Resampling.BICUBIC)

def frame(index):
    phase = index/(FPS*SECONDS)*math.tau
    image = base.copy()
    d = ImageDraw.Draw(image)
    for offset in (0, 2.4, 4.1):
        a = phase+offset
        px, py = 480+350*math.cos(a), 610+84*math.sin(a)
        d.ellipse((px-3,py-3,px+3,py+3), fill=(191,166,104,180))
    for layer in (2,1,0):
        points = [project(px,py,phase,layer) for px,py in ((0,0),(330,0),(330,455),(0,455))]
        image = Image.alpha_composite(image, warp(sheet(phase,layer), points))
    return image.convert('RGB')

first = frame(0)
first.save(OUT/'legal-motion-poster.webp', quality=88)
command = ['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}',
           '-r',str(FPS),'-i','-','-an','-c:v','libx264','-preset','slow','-crf','26','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'legal-motion.mp4')]
with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
    for i in range(FPS*SECONDS): encoder.stdin.write(frame(i).tobytes())
    encoder.stdin.close()
    if encoder.wait() != 0: raise RuntimeError('Video encoding failed')
print('Rendered original legal artwork:', [(p.name, p.stat().st_size) for p in OUT.glob('legal-motion*')])
