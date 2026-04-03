// Test same segment at different volumes

!volume 1.0
$segment2/1  // baseline

!volume 1.5
$segment2/1  // should be +3.5 dB louder

!volume 2.0
$segment2/1  // should be +6 dB louder
