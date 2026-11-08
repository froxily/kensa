<?php
require __DIR__ . '/segment.php';
$segments = [];
for ($number = 1; $number <= 100; $number++) {
    $segments[] = makeSegment();
    echo "Processed segment $number\n";
}
echo 'Segments: ' . count($segments) . "\n";
