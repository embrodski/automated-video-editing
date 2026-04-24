@echo off
setlocal

set "IN_VIDEO=E:\PodcastRoom\Cursor\Inkhaven Alice\Output\Full Reading.mp4"
set "IMG1=E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Diagram 1.jpg"
set "IMG2=E:\PodcastRoom\Cursor\Inkhaven Alice\Input\tidechart.png"
set "IMG3=E:\PodcastRoom\Cursor\Inkhaven Alice\Input\signoregalilei.png"
set "OUT_VIDEO=E:\PodcastRoom\Cursor\Inkhaven Alice\Output\Full Reading (with stills v2).mp4"

ffmpeg -y -i "%IN_VIDEO%" ^
  -loop 1 -framerate 30 -i "%IMG1%" ^
  -loop 1 -framerate 30 -i "%IMG2%" ^
  -loop 1 -framerate 30 -i "%IMG3%" ^
  -filter_complex "[0:v]setpts=PTS-STARTPTS[base];[1:v]setpts=PTS-STARTPTS,format=rgba[diagIn];[diagIn][base]scale2ref[diag][base1];[base1][diag]overlay=0:0:enable=between(t\,95\,101)[v1];[2:v]setpts=PTS-STARTPTS,format=rgba[tideIn];[tideIn][v1]scale2ref[tide][v2];[v2][tide]overlay=0:0:enable=between(t\,175\,180)[v3];[3:v]setpts=PTS-STARTPTS,format=rgba[logoIn];[logoIn][v3]scale2ref[logo][v4];[v4][logo]overlay=0:0:enable=between(t\,187\,195)[vout]" ^
  -map "[vout]" -map 0:a -c:v libx264 -preset veryfast -crf 18 -c:a copy -shortest ^
  "%OUT_VIDEO%"

exit /b %ERRORLEVEL%

