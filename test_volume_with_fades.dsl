// Test volume with fades to reproduce the issue

!camera speaker_0
!cut 50 50

!fade from black 100
!volume 1.0
$segment2/0

!volume 1.5
$segment2/1
!fade to black 100

!fade from black 100
!volume 0.7
$segment2/2
!fade to black 100

