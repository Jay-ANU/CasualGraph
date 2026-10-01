#!/bin/sh
# Encodes the rendered masters into the files the landing page serves.
set -eu
cd "$(dirname "$0")"
MEDIA=../../frontend/public/media
mkdir -p "$MEDIA"
encode() { # $1 master, $2 output name, $3 x264 crf, $4 vp9 crf
  ffmpeg -loglevel error -y -i "out/$1.mkv" -an -c:v libx264 -preset slow -crf "$3" -profile:v high -level 4.1 -pix_fmt yuv420p -g 60 -movflags +faststart "$MEDIA/$2.mp4"
  ffmpeg -loglevel error -y -i "out/$1.mkv" -an -c:v libvpx-vp9 -b:v 0 -crf "$4" -row-mt 1 -deadline good -cpu-used 2 -g 60 -pix_fmt yuv420p -pass 1 -passlogfile "out/$1" -f null /dev/null
  ffmpeg -loglevel error -y -i "out/$1.mkv" -an -c:v libvpx-vp9 -b:v 0 -crf "$4" -row-mt 1 -deadline good -cpu-used 2 -g 60 -pix_fmt yuv420p -pass 2 -passlogfile "out/$1" "$MEDIA/$2.webm"
}
encode landscape hero-legal-1080 24 37
encode portrait hero-legal-portrait 25 38
ffmpeg -loglevel error -y -i out/landscape.mkv -vf "select=eq(n\,0)" -frames:v 1 -c:v libwebp -quality 80 "$MEDIA/hero-legal-poster.webp"
ffmpeg -loglevel error -y -i out/portrait.mkv -vf "select=eq(n\,0)" -frames:v 1 -c:v libwebp -quality 80 "$MEDIA/hero-legal-poster-portrait.webp"
ls -la "$MEDIA"
