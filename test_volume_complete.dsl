// Comprehensive test: volume changes + fades + audio overlay

!camera speaker_0
!cut 50 50

// Normal volume
!volume 1.0
$segment2/0

// Volume up, add audio overlay here
!volume 1.5
!audio "Trailer FX 1effect.aif" 1.0
$segment2/1

// Volume down with fade
!volume 0.7
$segment2/2
!fade to black 100

// Back up with fade in
!fade from black 100
!volume 1.2
$segment2/3

