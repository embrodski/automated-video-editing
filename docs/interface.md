```python
vid1 = MP4Video("path1.mp4", offset=10) # Initializing this object looks up the duration of the video so that we can generate errors if invalid slices are taken.
vid2 = MP4Video("path2.mp4", offset=20)
vid3 = MP4Video("path3.mp4", offset=30)
audio1 = MP4Audio("audio1.mp4", offset=0)
audio2 = MP4Audio("audio2.mp4", offset=2000)

# This is saying that we want to start 10 seconds into audio 1 and play for 100 seconds from there. The video should start out as video 1, then after 2 seconds move to video 2, then at the 3 second mark move to video 3, then at the 7th second mark go to video 7, and continue that for the rest of the 100 seconds of the audio.
s1 = Scene(audio1, offset_in_audio=10, duration=100,
    clips = {
        0: vid1,
        2: vid2, 
        3: vid3,
        7: vid1
    })

# This scene uses a different clip of audio
s2 = Scene(audio2, offset_in_audio=30, duration=50,
    clips = {
        0: vid1,
        3.2: vid2, 
        3.8: vid3,
        5: vid1
    })

# This scene uses a different slice of the first audio clip.
s3 = Scene(audio3, offset_in_audio=200, duration=100,
    clips = {
        0: vid1,
        4: vid2, 
        8: vid3,
        12: vid2
    })

p = PodcastProject([s1, s2, s3])

m.render() # => renders the video together with the switches and the audio
m.render(start=20, duration=50) # => renders the video starting at 20 seconds in and with duration of 50.
m.render_audio() # => just renders the audio
```