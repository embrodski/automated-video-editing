// Test volume rendering with same clip at different volumes
// You should hear clear volume differences

!camera speaker_0
!cut 50 50

// Normal volume (100%)
!volume 1.0
$segment2/0

// Quiet (50%)
!volume 0.5
$segment2/0

// Loud (200%)
!volume 2.0
$segment2/0

// Very quiet (25%)
!volume 0.25
$segment2/0

