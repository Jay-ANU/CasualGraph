#!/bin/sh
# Encodes the rendered masters (out/*.mkv) into the files the landing page serves.
# Screen content with large flat areas compresses well; VP9 first, H.264 for Safari.
set -eu
cd "$(dirname "$0")"
MEDIA=../../frontend/public/media
mkdir -p "$MEDIA"
# The master opens on the window fading in; the web cut starts on the settled window so the
# poster (its first frame) and the film's first frame are the same picture.
encode() { # $1 master name, $2 output name, $3 width, $4 x264 crf, $5 vp9 crf
  ffmpeg -loglevel error -y -ss 1.0 -i "out/$1.mkv" -an -vf "scale=$3:-2:flags=lanczos" -c:v libx264 -preset slow -crf "$4" -profile:v high -level 4.2 -pix_fmt yuv420p -g 60 -movflags +faststart "$MEDIA/$2.mp4"
  ffmpeg -loglevel error -y -ss 1.0 -i "out/$1.mkv" -an -vf "scale=$3:-2:flags=lanczos" -c:v libvpx-vp9 -b:v 0 -crf "$5" -row-mt 1 -deadline good -cpu-used 2 -g 60 -pix_fmt yuv420p -pass 1 -passlogfile "out/$2" -f null /dev/null
  ffmpeg -loglevel error -y -ss 1.0 -i "out/$1.mkv" -an -vf "scale=$3:-2:flags=lanczos" -c:v libvpx-vp9 -b:v 0 -crf "$5" -row-mt 1 -deadline good -cpu-used 2 -g 60 -pix_fmt yuv420p -pass 2 -passlogfile "out/$2" "$MEDIA/$2.webm"
  ffmpeg -loglevel error -y -ss 1.0 -i "out/$1.mkv" -vf "scale=$3:-2:flags=lanczos" -frames:v 1 -c:v libwebp -quality 82 "$MEDIA/$2-poster.webp"
}
for lang in zh en; do
  encode "$lang-landscape" "film-$lang-landscape" 1920 26 36
  encode "$lang-portrait" "film-$lang-portrait" 810 26 36
done
ls -la "$MEDIA"
